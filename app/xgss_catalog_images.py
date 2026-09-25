"""Offline rendering of bounded XGSS drawings, including embedded JPEG/PNG.

The drawing is never allowed to load a URL or local file. Embedded rasters are
decoded and re-encoded before resvg sees them; only standalone SVG is rendered.
"""
import base64
import binascii
import hashlib
from io import BytesIO
import math
import re
from xml.etree import ElementTree as ET

from app import xgss_research_images as images

MAX_SVG_BYTES = 4 * 1024 * 1024
MAX_EMBEDDED_BYTES = 4 * 1024 * 1024
MAX_EMBEDDED_PIXELS = 8_000_000
MAX_DRAWING_SHEETS = 4
SVG_NS = 'http://www.w3.org/2000/svg'


class CatalogImageError(ValueError):
    pass


class RendererUnavailable(CatalogImageError):
    pass


def _embedded_png(value, budget):
    """Accept only self-contained raster data; no nested SVG or resource lookup."""
    match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)', value, re.I)
    if not match or images.Image is None:
        raise ValueError()
    encoded = re.sub(r'\s+', '', match[2])
    if len(encoded) > 4 * ((MAX_EMBEDDED_BYTES + 2) // 3):
        raise ValueError()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError() from None
    budget['bytes'] += len(raw)
    if not raw or budget['bytes'] > MAX_EMBEDDED_BYTES:
        raise ValueError()
    expected = {'png': 'PNG', 'jpeg': 'JPEG'}[match[1].lower()]
    with images.Image.open(BytesIO(raw)) as raster:
        width, height = raster.size
        budget['pixels'] += width * height
        if (raster.format != expected or getattr(raster, 'n_frames', 1) != 1
                or min(width, height) <= 0 or max(width, height) > images.MAX_IMAGE_SIDE
                or budget['pixels'] > MAX_EMBEDDED_PIXELS):
            raise ValueError()
        raster.verify()
    with images.Image.open(BytesIO(raw)) as raster:
        raster.load()
        output = BytesIO()
        # Discard metadata and profiles as well as the original encoded input.
        clean = images.Image.new('RGBA' if 'A' in raster.getbands() else 'RGB', raster.size)
        clean.paste(raster)
        clean.save(output, format='PNG', optimize=True)
    data = output.getvalue()
    budget['decoded_bytes'] += len(data)
    if budget['decoded_bytes'] > MAX_EMBEDDED_BYTES:
        raise ValueError()
    return images.PNG_PREFIX + base64.b64encode(data).decode('ascii')


def rasterize_svg(raw):
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SVG_BYTES:
        raise CatalogImageError('图纸文件超出读取范围。')
    try:
        from defusedxml.ElementTree import fromstring
        import resvg_py
    except ImportError:
        raise RendererUnavailable('图纸转换组件未安装，可使用网页读取。') from None
    try:
        root = fromstring(raw, forbid_entities=True, forbid_external=True)
        if root.tag != '{' + SVG_NS + '}svg':
            raise ValueError()
        allowed = {'svg', 'g', 'path', 'line', 'polyline', 'polygon', 'rect', 'circle', 'ellipse',
                   'text', 'tspan', 'defs', 'use', 'symbol', 'clipPath', 'mask', 'style',
                   'linearGradient', 'radialGradient', 'stop', 'title', 'desc', 'image'}
        budget = {'bytes': 0, 'pixels': 0, 'decoded_bytes': 0}
        for count, node in enumerate(root.iter(), 1):
            tag = node.tag.removeprefix('{' + SVG_NS + '}')
            if count > 100000 or tag not in allowed:
                raise ValueError()
            image_links = 0
            for key, value in list(node.attrib.items()):
                local = key.split('}')[-1]
                if local.lower().startswith('on') or local == 'base':
                    raise ValueError()
                if local in ('href', 'src'):
                    if tag == 'image' and local == 'href':
                        image_links += 1
                        node.set(key, _embedded_png(value, budget))
                        continue
                    if not re.fullmatch(r'#[\w.:-]+', value):
                        raise ValueError()
                if re.search(r'@import|@font-face|expression\s*\(|\\', value, re.I):
                    raise ValueError()
                for match in re.findall(r'url\s*\((.*?)\)', value, re.I):
                    if not re.fullmatch(r'[\s\"\x27]*#[\w.:-]+[\s\"\x27]*', match):
                        raise ValueError()
            if tag == 'image' and image_links != 1:
                raise ValueError()
            if tag == 'style' and re.search(r'@|\\|url\s*\(', node.text or '', re.I):
                raise ValueError()
        box = [float(v) for v in re.split(r'[\s,]+', root.get('viewBox', '').strip()) if v]
        if len(box) == 4:
            width, height = box[2:]
        else:
            width = float(re.fullmatch(r'([0-9.]+)(?:px|mm|cm|in|pt)?', root.get('width', '')).group(1))
            height = float(re.fullmatch(r'([0-9.]+)(?:px|mm|cm|in|pt)?', root.get('height', '')).group(1))
        if not all(math.isfinite(v) and v > 0 for v in (width, height)) or not .03 < width / height < 30:
            raise ValueError()
        scale = 1600 / max(width, height)
        out_width, out_height = max(1, round(width * scale)), max(1, round(height * scale))
        root.set('width', str(out_width))
        root.set('height', str(out_height))
        ET.register_namespace('', SVG_NS)
        ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
        png = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding='unicode'),
                                   width=out_width, height=out_height, background='white', log_information=False)
        images.validate_png(png)
        return png
    except Exception:
        raise CatalogImageError('图纸格式或内嵌图片未通过校验，未使用该图。') from None


def sheet_illustration(sheets, *, title, total):
    """Make an explicitly labelled category contact sheet, never a row mapping.

    sheets contains (one-based source sheet position, document reference, PNG).
    The source index remains visible when only some sheets were readable.
    """
    if not 1 <= len(sheets) <= MAX_DRAWING_SHEETS or not len(sheets) <= total <= 30:
        raise CatalogImageError('图纸页数超出读取范围。')
    for index, document, png in sheets:
        if not isinstance(index, int) or not 1 <= index <= total or not re.fullmatch(r'[1-9][0-9]*\.svg', document):
            raise CatalogImageError('图纸页码无法核对。')
        images.validate_png(png)
    if total == 1:
        _, document, png = sheets[0]
        return {'data_url': images.PNG_PREFIX + base64.b64encode(png).decode('ascii'),
                'title': title, 'document_ref': document}
    from PIL import Image, ImageDraw, ImageFont
    cols = min(2, len(sheets))
    rows = math.ceil(len(sheets) / cols)
    size, gutter, label_height = 1300, 16, 36
    board = Image.new('RGB', (cols * (size + gutter) + gutter,
                              rows * (size + label_height + gutter) + gutter), 'white')
    draw = ImageDraw.Draw(board)
    font = ImageFont.load_default(size=22)
    for position, (index, document, png) in enumerate(sheets):
        x, y = gutter + position % cols * (size + gutter), gutter + position // cols * (size + label_height + gutter)
        draw.text((x, y), f'Sheet {index}/{total} | {document}', fill='black', font=font)
        with Image.open(BytesIO(png)) as raster:
            raster = raster.convert('RGB')
            raster.thumbnail((size, size), Image.Resampling.LANCZOS)
            board.paste(raster, (x + (size - raster.width) // 2, y + label_height))
    output = BytesIO()
    board.save(output, format='PNG', optimize=True)
    png = output.getvalue()
    images.validate_png(png)
    refs = '|'.join(document for _, document, _ in sheets)
    suffix = f' · 图册页 {"、".join(str(index) for index, _, _ in sheets)}（共 {total} 页）'
    return {'data_url': images.PNG_PREFIX + base64.b64encode(png).decode('ascii'),
            'title': title[:200 - len(suffix)] + suffix,
            'document_ref': 'sheets-' + hashlib.sha256(refs.encode('ascii')).hexdigest()[:32] + '.png'}
