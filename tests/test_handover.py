"""The handover must not send the next person down a path that no longer exists.

It is written for someone who has never seen the project, so a stale command or a wrong
version number costs them real time before they discover it. It also records the mistakes
made while building this, and those warnings are the most valuable part — a test that the
warnings are still present keeps them from being tidied away.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
HANDOVER = DOCS / '交接文档.md'


@pytest.fixture(scope='module')
def handover() -> str:
    assert HANDOVER.is_file(), 'the handover document is missing'
    return HANDOVER.read_text(encoding='utf-8')


def test_its_links_resolve(handover):
    missing = [target for target in re.findall(r'\]\(([^)]+)\)', handover)
               if not target.startswith(('http://', 'https://', '#'))
               and not (DOCS / target).exists()]
    assert missing == [], f'the handover links to files that do not exist: {missing}'


def test_every_command_it_gives_exists(handover):
    for name in re.findall(r'scripts[\\/]([A-Za-z0-9_]+\.(?:py|mjs))', handover):
        assert (ROOT / 'scripts' / name).is_file(), f'{name} is missing'
    assert (ROOT / 'start_local.cmd').is_file()


def test_the_quoted_plugin_version_matches_the_manifest(handover):
    version = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))['version']
    assert f'`{version}`' in handover or version in handover, \
        f'the handover must quote the current extension version {version}'


def test_the_data_source_it_describes_is_the_one_configured(handover):
    # It tells the reader which source is active; a mismatch sends them looking at the
    # wrong machines immediately.
    from app.data_store import get_data_source
    assert get_data_source() in handover, \
        f'the handover must name the active source ({get_data_source()})'


def test_it_names_the_environment_traps_that_cost_time(handover):
    """These are the mistakes made while building this, and they are not guessable."""
    assert 'override=True' in handover, 'the .env override trap must be recorded'
    assert 'mock_data' in handover and '共享夹具' in handover, \
        'the shared-fixture trap must be recorded'
    assert 'KNOWLEDGE_PATH' in handover, 'the monkeypatch trap must be recorded'
    assert '静默跳过' in handover, 'the silently-skipped-tests trap must be recorded'
    assert 'pydantic' in handover, 'the pin constraint must be recorded'


def test_it_warns_against_running_the_whole_suite_repeatedly(handover):
    # Running the full suite over and over crashed this machine during the build.
    assert '不要反复跑全量测试' in handover
    assert '闪退' in handover


def test_it_states_the_three_manual_checks(handover):
    assert '人工' in handover
    assert '浏览器侧边栏' in handover
    assert '真实 XGSS 页面' in handover


def test_it_states_what_must_not_be_faked(handover):
    # The honesty rules are load-bearing: they are why the demo can be shown at all.
    assert '不要为了演示效果伪造数据' in handover
    assert '准确率' in handover
    assert 'H10101' in handover, 'it must record that the scripted case is gone'


def test_it_points_at_the_current_interface_not_the_legacy_one(handover):
    assert 'assistant_ui' in handover
    assert '遗留' in handover and 'frontend/' in handover, \
        'it must warn that frontend/ is not the current interface'


def test_the_test_counts_it_quotes_are_current(handover):
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q'],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    collected = re.search(r'(\d+) tests? collected', result.stdout)
    if not collected:
        pytest.skip('collection output was not in the expected form')
    total = int(collected.group(1))
    quoted = [int(value) for value in re.findall(r'Python (\d+) 项', handover)]
    assert quoted, 'the handover must quote a Python test count'
    assert any(total - 12 <= value <= total for value in quoted), \
        f'the handover quotes {quoted} but collection reports {total}'


def test_it_flags_the_manual_redistribution_question(handover):
    # The excerpts were copied to a distributable location on a verbal confirmation only.
    assert '授权' in handover and '书面依据' in handover


def test_it_records_that_commits_are_unpushed(handover):
    assert '未推送' in handover


def test_it_is_long_enough_to_be_useful_and_short_enough_to_finish(handover):
    lines = handover.split('\n')
    assert 120 <= len(lines) <= 330, f'{len(lines)} lines is outside the useful range'
