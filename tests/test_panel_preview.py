"""The panel preview route exists for local checks and must stay tightly scoped.

The side panel is normally loaded by Chrome from an extension. Serving it over the
workbench's own origin lets a local check drive the panel and the workbench frame
together, which a `file://` page cannot do because its origin is null. That
convenience must not turn into publishing the extension package: the manifest and the
icons stay out, so the extension id and icon set are not handed out.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import _PANEL_FILES, app

SERVED = ['panel.html', 'panel.js', 'panel.css', 'context.js', 'xgss-catalog.js',
          'assets/xcmg-logo.png']
WITHHELD = ['manifest.json', 'README.md', '../app/main.py', 'assets/icon128.png',
            'background.js', 'nope.js', '']


@pytest.fixture(scope='module')
def client():
    return TestClient(app)


@pytest.mark.parametrize('name', SERVED)
def test_the_panel_files_the_page_loads_are_served(client, name):
    response = client.get(f'/panel-preview/{name}')
    assert response.status_code == 200, f'{name} is loaded by panel.html and must be served'
    assert response.headers['cache-control'] == 'no-store', \
        'a cached copy would let a check report the previous revision as current'
    assert len(response.content) > 0


@pytest.mark.parametrize('name', WITHHELD)
def test_anything_outside_the_allowlist_is_not_served(client, name):
    response = client.get(f'/panel-preview/{name}')
    assert response.status_code == 404, f'{name} must not be published by the preview route'


def test_the_manifest_is_deliberately_withheld():
    # It carries the extension identity; publishing it costs the project something and
    # gains a local check nothing.
    assert 'manifest.json' not in _PANEL_FILES
    assert not any('icon' in name for name in _PANEL_FILES), \
        'the icon set is not needed by the page and stays out of the preview'


def test_the_allowlist_matches_what_panel_html_actually_references():
    """A file the page loads but the route withholds would 404 in the preview."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / 'extension/panel.html').read_text(encoding='utf-8')
    referenced = []
    for match in re.finditer(r'(?:src|href)="([^"]+)"', html):
        target = match.group(1)
        if target.startswith(('http', 'data:', '#')):
            continue
        referenced.append(target)
    missing = [name for name in referenced if name not in _PANEL_FILES]
    assert missing == [], f'panel.html loads {missing} but the preview route does not serve them'
