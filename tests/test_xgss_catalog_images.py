"""Regression tests for real XGSS export shapes; no external data/API required."""
import base64
from io import BytesIO

import httpx
from PIL import Image
import pytest

from app import xgss_direct_api as api
from app import xgss_catalog_images as renderer
from test_xgss_direct_api import upstream, VIN, DETAIL, SVG


def embedded_svg(format='JPEG', mime='jpeg', *, width=100, height=100):
    raster = Image.new('RGB', (width, height), '#153d67')
    output = BytesIO()
    raster.save(output, format=format)
    encoded = base64.b64encode(output.getvalue()).decode()
    encoded = '\n'.join(encoded[i:i + 72] for i in range(0, len(encoded), 72))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 100 100"><image width="100" height="100" '
            f'xlink:href="data:image/{mime};base64,{encoded}"/></svg>').encode()


@pytest.mark.parametrize('format,mime', [('JPEG', 'jpeg'), ('PNG', 'png')])
def test_adobe_embedded_raster_export_renders_visible_pixels(format, mime):
    png = api.svg_png(embedded_svg(format, mime))
    assert renderer.images.validate_png(png) == (1600, 1600)
    with Image.open(BytesIO(png)) as image:
        red, green, blue, *_ = image.getpixel((800, 800))
        assert red < 60 and green < 100 and blue < 140


@pytest.mark.parametrize('href', [
    'file:///private.png', 'https://outside.invalid/p.png', '//outside.invalid/p.png',
    'data:image/svg+xml;base64,PHN2Zy8+', 'data:image/png;base64,bm90IGEgcG5n',
])
def test_embedded_image_cannot_be_external_nested_svg_or_invalid_bytes(href):
    raw = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
           f'<image width="100" height="100" href="{href}"/></svg>').encode()
    with pytest.raises(api.DirectReadError) as error:
        api.svg_png(raw)
    assert error.value.kind == 'direct_image'


def test_embedded_image_declared_format_must_match_decoded_bytes():
    with pytest.raises(api.DirectReadError):
        api.svg_png(embedded_svg('JPEG', 'png'))


def test_embedded_image_pixel_budget_is_enforced_before_rendering(monkeypatch):
    monkeypatch.setattr(renderer, 'MAX_EMBEDDED_PIXELS', 9999)
    with pytest.raises(api.DirectReadError):
        api.svg_png(embedded_svg())


def test_multisheet_category_keeps_labelled_contact_sheet(upstream):
    upstream[1]['/api/rest/partlist/view/30/10'] = {**DETAIL, 'd2ids': ['3944444.svg', '3944445.svg']}
    result = api.collect_catalog(VIN, ['双变系统'])
    assert result['status'] == 'completed'
    image = result['pages'][0]['illustrations'][0]
    assert image['document_ref'].startswith('sheets-')
    assert '图册页 1、2（共 2 页）' in image['title']
    assert sum('/image2d/' in path for _, path, _ in upstream[0]) == 2
    png = base64.b64decode(image['data_url'].split(',', 1)[1])
    width, height = renderer.images.validate_png(png)
    assert width > height and width * height <= renderer.images.MAX_IMAGE_PIXELS


@pytest.mark.parametrize('failure,attempts', [
    (httpx.Response(404), 1), (httpx.Response(503), 2), (httpx.ReadTimeout('private detail'), 2),
])
def test_missing_or_transient_diagram_retains_verified_part_rows(upstream, failure, attempts):
    upstream[1]['/api/doc/image2d/3944444.svg'] = failure
    result = api.collect_catalog(VIN, ['双变系统'])
    assert result['status'] == 'partial'
    assert result['pages'][0]['items'][0]['part_number'] == '800365540'
    assert result['pages'][0]['illustrations'] == []
    assert any('零件资料已保留' in issue for issue in result['unresolved'])
    assert sum('/image2d/' in path for _, path, _ in upstream[0]) == attempts
    assert all('private detail' not in issue for issue in result['unresolved'])


@pytest.mark.parametrize('status', [401, 403, 302])
def test_image_auth_or_redirect_failure_still_stops(upstream, status):
    upstream[1]['/api/doc/image2d/3944444.svg'] = httpx.Response(status)
    with pytest.raises(api.DirectReadError):
        api.collect_catalog(VIN, ['双变系统'])


def test_partial_contact_sheet_does_not_relabel_source_page(upstream):
    upstream[1]['/api/rest/partlist/view/30/10'] = {**DETAIL, 'd2ids': ['3944444.svg', '3944445.svg']}
    upstream[1]['/api/doc/image2d/3944444.svg'] = httpx.Response(404)
    result = api.collect_catalog(VIN, ['双变系统'])
    assert result['status'] == 'partial'
    assert '图册页 2（共 2 页）' in result['pages'][0]['illustrations'][0]['title']


def test_document_page_budget_is_explicit_and_bounded(upstream):
    docs = [f'{3944444 + index}.svg' for index in range(6)]
    upstream[1]['/api/rest/partlist/view/30/10'] = {**DETAIL, 'd2ids': docs}
    result = api.collect_catalog(VIN, ['双变系统'])
    assert result['status'] == 'partial'
    assert '共 6 页' in result['pages'][0]['illustrations'][0]['title']
    assert sum('/image2d/' in path for _, path, _ in upstream[0]) == 4
    assert any('其余图纸' in issue for issue in result['unresolved'])


def test_request_budget_preserves_rows_when_later_image_cannot_start(upstream, monkeypatch):
    monkeypatch.setattr(api, 'MAX_REQUESTS', 4)
    upstream[1]['/api/rest/partlist/view/30/10'] = {**DETAIL, 'd2ids': ['3944444.svg', '3944445.svg']}
    # Exercise page collection directly; outer traversal reserves category budget.
    client = api.CatalogClient(VIN, lambda: None, lambda _: None)
    try:
        client.authenticate()
        root = client.node({'id': 10, 'code': VIN, 'name': 'XC948'})
        node = client.node({'id': 20, 'code': '252808033', 'name': '双变系统'})
        pages, issues = client.pages(node, root, ['XC948', '双变系统'], 1)
        assert len(pages) == 1 and pages[0]['items']
        assert '图册页 1（共 2 页）' in pages[0]['illustrations'][0]['title']
        assert any('尚未读取' in issue for issue in issues)
    finally:
        client.close()
