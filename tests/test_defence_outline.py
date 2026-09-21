"""The defence outline must point at things that exist and figures that are current.

It replaces a deck that described features which have since been deleted, so the failure
mode to guard against is the same one: a slide claiming something the project no longer
does. Every command, file and number it cites is checked here.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
OUTLINE = DOCS / '答辩演示稿大纲.md'


@pytest.fixture(scope='module')
def outline() -> str:
    assert OUTLINE.is_file(), 'the defence outline is missing'
    return OUTLINE.read_text(encoding='utf-8')


def test_its_links_resolve(outline):
    missing = [target for target in re.findall(r'\]\(([^)]+)\)', outline)
               if not target.startswith(('http://', 'https://', '#'))
               and not (DOCS / target).exists()]
    assert missing == [], f'the outline links to files that do not exist: {missing}'


def test_every_command_it_tells_the_presenter_to_run_exists(outline):
    scripts = re.findall(r'scripts[\\/]([A-Za-z0-9_]+\.(?:py|mjs))', outline)
    assert scripts, 'the outline must name the commands it asks the presenter to run'
    for name in scripts:
        assert (ROOT / 'scripts' / name).is_file(), f'{name} is missing'


def test_it_does_not_revive_the_deleted_materials(outline):
    # The deck this replaces taught the scripted case and the cooling experiment; both have
    # been removed from the product, so the new outline must not send anyone back to them.
    # The warning at the top is allowed to name them — that is how a reader learns the old
    # deck is superseded — so only the pages themselves are checked.
    pages = outline.split('## 制作提示')[0]
    pages = re.sub(r'^> .*$', '', pages, flags=re.M)  # drop the blockquote warning
    for stale in ('H10101', '冷却预警实验', '工况识别实验', '讲解案例（模拟）', 'demo-case'):
        assert stale not in pages, f'a slide must not reference the removed {stale}'
    assert '不要沿用' in outline, 'it must warn that the old deck is superseded'


def test_the_quoted_figures_match_the_source(outline):
    # 63 references / 0 dangling is recomputed here rather than trusted, so a stale number
    # in the deck fails instead of being read out.
    from app.ai_grounding_report import build_report
    data = build_report(ROOT / 'data/local/investigations')
    totals = data['totals']
    if totals['records_with_model'] == 0:
        pytest.skip('no saved AI runs on this machine to compare against')
    if totals['dangling'] == 0:
        assert f"{totals['checked']} 条引用" in outline, \
            f"the outline should quote {totals['checked']} checked references"
        assert '0 条悬空' in outline
    else:
        assert '0 条悬空' not in outline, \
            f"the outline claims no dangling citations but records show {totals['dangling']}"


def test_the_quoted_test_counts_match_reality(outline):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q'],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    collected = re.search(r'(\d+) tests? collected', result.stdout)
    if not collected:
        pytest.skip('collection output was not in the expected form')
    total = int(collected.group(1))
    quoted = [int(value) for value in re.findall(r'Python (\d+) 项', outline)]
    assert quoted, 'the outline must quote a Python test count'
    assert any(total - 12 <= value <= total for value in quoted), \
        f'the outline quotes {quoted} but collection reports {total}'


def test_the_timing_adds_up_to_the_stated_length(outline):
    # A deck whose timings do not fit the slot is a deck that gets cut mid-sentence.
    slots = re.findall(r'（(\d+):(\d+)—(\d+):(\d+)）', outline)
    assert slots, 'each page must carry a suggested time'
    def seconds(minutes, secs):
        return int(minutes) * 60 + int(secs)
    assert seconds(*slots[0][:2]) == 0, 'the deck must start at 0:00'
    end = seconds(*slots[-1][2:])
    assert 540 <= end <= 660, f'the deck runs to {end // 60}:{end % 60:02d}, outside a 9-11 minute slot'


def test_it_names_the_honesty_pages(outline):
    # The boundary page and the provenance page are why the deck can be trusted; losing
    # them would turn it into an ordinary product pitch.
    assert '诚实边界' in outline
    assert '不声称诊断正确率' in outline
    assert '合成' in outline and '真实' in outline
    assert '仍需人工' in outline


def test_it_names_the_real_browser_probes(outline):
    for probe in ('extension_probe.mjs', 'xgss_marking_probe.mjs', 'sidebar_guidance_probe.mjs'):
        assert probe in outline, f'the outline must point at {probe}'


def test_it_stays_short_enough_to_actually_build(outline):
    assert len(outline.split('\n')) <= 340, 'an outline longer than this will not become a deck'
