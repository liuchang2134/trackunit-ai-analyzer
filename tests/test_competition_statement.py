"""The competition statement quotes figures; those figures must stay true.

A hand-written summary that drifts from the code is worse than no summary: it is
the document a reviewer reads first, and a stale number in it discredits every
other claim. These tests bind the statement's quoted figures to the artefacts they
come from.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
STATEMENT = DOCS / '参赛说明.md'
LINK = re.compile(r'\]\(([^)]+)\)')


@pytest.fixture(scope='module')
def statement() -> str:
    assert STATEMENT.is_file(), 'the competition statement is missing'
    return STATEMENT.read_text(encoding='utf-8')


def test_the_statement_links_resolve(statement):
    missing = [target for target in LINK.findall(statement)
               if not target.startswith(('http://', 'https://', '#'))
               and not (DOCS / target).exists()]
    assert missing == [], f'the statement links to files that do not exist: {missing}'


def test_the_quoted_extension_version_matches_the_manifest(statement):
    version = json.loads((ROOT / 'extension/manifest.json').read_text(encoding='utf-8'))['version']
    assert f'`{version}`' in statement, f'the statement must quote the extension version {version}'


def test_the_quoted_build_id_matches_the_source(statement):
    build = (ROOT / 'app/assistant_version.py').read_text(encoding='utf-8')
    match = re.search(r"ASSISTANT_BUILD\s*=\s*'([^']+)'", build)
    assert match, 'the build id must be readable from assistant_version.py'
    assert match.group(1) in statement, 'the statement must quote the current build id'


def test_the_quoted_test_count_is_current(statement):
    """Compare the quoted figure with collection, without running the suite again.

    Running pytest from inside a test would re-enter this very test and recurse
    until timeout, so the check collects instead. Collection counts the tests that
    skip by design when private material is absent, so the quoted passing figure
    sits just below the collected one; a stale figure drifts outside that window.
    """
    import subprocess
    import sys

    result = subprocess.run([sys.executable, '-m', 'pytest', 'tests', '--collect-only', '-q'],
                            cwd=ROOT, capture_output=True, text=True, timeout=300)
    collected = re.search(r'(\d+) tests? collected', result.stdout)
    if not collected:
        pytest.skip('collection output was not in the expected form')
    total = int(collected.group(1))
    quoted = [int(value) for value in re.findall(r'Python (\d+)', statement)]
    assert quoted, 'the statement must quote a Python test count'
    assert any(total - 12 <= value <= total for value in quoted), \
        f'the statement quotes {quoted} but collection reports {total}; update the statement'


def test_the_grounding_figures_are_recomputable_and_match_the_newest_report(statement):
    from app.ai_grounding_report import build_report
    data = build_report(ROOT / 'data/local/investigations')
    totals = data['totals']
    if totals['records_with_model'] == 0:
        pytest.skip('no saved AI runs on this machine to compare against')
    # The statement's headline is that no citation dangles; if that ever changes the
    # statement must be corrected rather than left claiming a clean result.
    if totals['dangling'] == 0:
        assert '0 条悬空' in statement
    else:
        assert '0 条悬空' not in statement, \
            f"the statement claims no dangling citations but the records show {totals['dangling']}"


def test_the_statement_declares_what_it_does_not_claim(statement):
    # These sentences are the reason the document can be trusted; losing them would
    # turn a measured statement into a marketing claim.
    assert '不是诊断正确率' in statement
    assert '不作任何准确率声明' in statement
    assert '样本量很小' in statement
    assert '待核查方向' in statement
    assert '不是性能基准' in statement


def test_the_statement_names_the_checks_that_need_a_person(statement):
    # The boundary moved as verification improved: the sidebar and the catalog marking
    # are now driven in a real browser, so the statement must not keep claiming they are
    # entirely unverified — and it must still name what only a person can finish.
    assert '人工完成' in statement, 'the statement must name the manual checks'
    assert '作为浏览器侧边栏' in statement, 'opening the side panel needs a user gesture'
    assert '已登录的真实 XGSS 页面' in statement, 'the real catalog needs the engineer login'
    assert '尚未端到端验证' in statement, \
        'rendering the terms in the sidebar still needs the real extension origin'


def test_the_statement_reports_the_ai_as_verified_in_a_real_browser(statement):
    for probe in ('extension_probe.mjs', 'xgss_marking_probe.mjs', 'sidebar_guidance_probe.mjs'):
        assert probe in statement, f'the statement must point at {probe}'


def test_the_statement_records_the_seam_defect_it_fixed(statement):
    # A worked example of "looks connected, actually broken" is the strongest evidence
    # that the verification is real rather than decorative.
    assert '诊断记录' in statement and '检索词' in statement
    assert '接缝' in statement
    assert '修复前' in statement and '修复后' in statement


def test_the_statement_names_the_provider_actually_in_use(statement):
    build = (ROOT / 'app/assistant_version.py').read_text(encoding='utf-8')
    assert build  # the build id exists; provider defaults live in .env and the client
    client = (ROOT / 'app/deepseek_client.py').read_text(encoding='utf-8')
    assert 'DEFAULT_DEEPSEEK_MODEL' in client
    assert 'DeepSeek' in statement, 'the statement must name the provider the project uses'


def test_the_statement_is_short_enough_to_be_read_before_a_demo(statement):
    # A statement nobody reads is not a deliverable; keep it a couple of pages.
    assert len(statement.split('\n')) <= 140, 'the statement has grown past a quick read'


def test_the_statement_says_how_to_reproduce_the_figures(statement):
    assert 'evaluate_ai_grounding.py' in statement
    assert 'pytest' in statement
