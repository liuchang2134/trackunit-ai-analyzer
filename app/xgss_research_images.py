"""Bounded PNG bytes from the rendered XGSS page; never fetch a supplied URL."""
import base64
import binascii
import hashlib
from io import BytesIO
import os
import re
import struct
import tempfile

from pydantic import BaseModel, ConfigDict, Field

try:
    from PIL import Image
except ImportError:  # Keep text-only research available without the optional decoder.
    Image = None

PNG_PREFIX = 'data:image/png;base64,'
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_SIDE = 4096
MAX_IMAGE_PIXELS = 8_000_000
MAX_RESEARCH_IMAGE_BYTES = 8 * 1024 * 1024
DOCUMENT_REF_PATTERN = r'^[A-Za-z0-9_-]{1,100}(?:\.[A-Za-z0-9]{1,10})?$'


class ImageCaptureError(ValueError):
    """A diagram could not be verified or persisted within the image bounds."""


class IllustrationCapture(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    data_url: str = Field(min_length=len(PNG_PREFIX) + 1,
                          max_length=len(PNG_PREFIX) + 4 * ((MAX_IMAGE_BYTES + 2) // 3),
                          pattern=r'^data:image/png;base64,[A-Za-z0-9+/]*={0,2}$')
    title: str = Field(min_length=1, max_length=200)
    document_ref: str = Field(pattern=DOCUMENT_REF_PATTERN)


class IllustrationMetadata(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    image_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: str = Field(min_length=1, max_length=200)
    document_ref: str = Field(pattern=DOCUMENT_REF_PATTERN)
    width: int = Field(ge=1, le=MAX_IMAGE_SIDE, strict=True)
    height: int = Field(ge=1, le=MAX_IMAGE_SIDE, strict=True)
    captured_at: str = Field(min_length=1, max_length=80)


def validate_png(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImageCaptureError('图册图片超过单张 2 MiB 限制，未保存本页。')
    if len(data) < 33 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ImageCaptureError('图册图片必须是有效 PNG，不能提交 SVG 或图片地址。')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height or max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        raise ImageCaptureError('图册图片尺寸超过 4096 像素边长或 800 万像素限制，未保存本页。')
    if Image is None:
        raise ImageCaptureError('当前环境无法校验 PNG 图片，未保存本页。')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != 'PNG' or image.size != (width, height) or getattr(image, 'n_frames', 1) != 1:
                raise ImageCaptureError('图册图片必须是单帧 PNG。')
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
    except ImageCaptureError:
        raise
    except (OSError, SyntaxError, ValueError) as error:
        raise ImageCaptureError('图册 PNG 图片不完整或校验失败，未保存本页。') from error
    return width, height


def prepare(capture):
    try:
        data = base64.b64decode(capture.data_url[len(PNG_PREFIX):], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ImageCaptureError('图册图片编码无效，未保存本页。') from error
    width, height = validate_png(data)
    return data, {'image_id': hashlib.sha256(data).hexdigest(), 'title': capture.title,
                  'document_ref': capture.document_ref, 'width': width, 'height': height}


def path_for(folder, image_id):
    if not isinstance(image_id, str) or not re.fullmatch(r'[a-f0-9]{64}', image_id):
        raise ImageCaptureError('无效的图册图片编号。')
    return folder / (image_id + '.png')


def read_blob(folder, metadata):
    metadata = IllustrationMetadata.model_validate(metadata)
    data = path_for(folder, metadata.image_id).read_bytes()
    if hashlib.sha256(data).hexdigest() != metadata.image_id:
        raise ImageCaptureError('图册图片校验失败。')
    if validate_png(data) != (metadata.width, metadata.height):
        raise ImageCaptureError('图册图片尺寸与来源记录不一致。')
    return data


def write_blob(folder, image_id, data):
    """Atomic content-addressed write. Return whether a new blob was created."""
    path = path_for(folder, image_id)
    if path.exists():
        if path.read_bytes() != data:
            raise ImageCaptureError('已有图册图片校验失败，未覆盖原文件。')
        return False
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=folder, delete=False) as stream:
            temporary = stream.name
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return True
