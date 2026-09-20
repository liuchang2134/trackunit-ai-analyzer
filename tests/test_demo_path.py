"""The demo path must be followable, so every step in it has to be real.

A walkthrough that names a command that no longer exists, or a screen element that was
renamed, wastes the reviewer's time and makes the project look unmaintained. These
tests bind the document to the artefacts it points at.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
DEMO = DOCS / '演示路径.md'
LINK = re.compile(r'\]\(([^)]+)\)')
COMMAND = re.compile(r'^\s*(?:\.tmp\\venv\\Scripts\\python\.exe|node|start_local\.cmd)\s+\S+', re.M)


@pytest.fixture(scope='module')
def demo() -> str:
    assert DEMO.is_file(), 'the demo path document is missing'
    return DEMO.read_text(encoding='utf-8')


def test_its_links_resolve(demo):
    missing = [target for target in LINK.findall(demo)
               if not target.startswith(('http://', 'https://', '#'))
               and not (DOCS / target).exists()]
    assert missing == [], f'the demo path links to files that do not exist: {missing}'


def test_every_script_it_tells_the_reviewer_to_run_exists(demo):
    scripts = re.findall(r'scripts[\\/]([A-Za-z0-9_]+\.(?:py|mjs))', demo)
    assert scripts, 'the demo path must name the scripts it asks a reviewer to run'
    missing = [name for name in scripts if not (ROOT / 'scripts' / name).is_file()]
    assert missing == [], f'the demo path names scripts that do not exist: {missing}'


def test_the_launcher_it_names_exists(demo):
    assert 'start_local.cmd' in demo
    assert (ROOT / 'start_local.cmd').is_file()


def test_it_points_at_screens_that_actually_exist(demo):
    # Each label here is a real control in index.html or panel.html; renaming the UI
    # without updating the walkthrough would leave a reviewer hunting for it.
    index = (ROOT / 'app/assistant_ui/index.html').read_text(encoding='utf-8')
    panel = (ROOT / 'extension/panel.html').read_text(encoding='utf-8')
    for label in ('演示案例', '真实 AI 记录回放', '设备排查', 'AI 辅助排查',
                  '本次排查中 AI 做了什么', '下载 AI 排查证据包'):
        assert label in demo, f'the walkthrough must mention {label}'
    assert '真实 AI 记录回放' in index, 'the replay tab label must exist in the page'
    assert 'AI 辅助排查' in index
    assert '读取设备' in panel and '图册' in panel, 'the sidebar bar labels must exist'


def test_it_says_which_steps_need_a_key(demo):
    # Most of the walkthrough is offline; a reviewer needs to know that before starting.
    assert '[无需密钥]' in demo and '[需密钥]' in demo
    assert '全部可离线完成' in demo or '全部无需密钥' in demo


def test_it_states_what_the_walkthrough_does_not_prove(demo):
    assert '没证明诊断准确率' in demo
    assert '样本量小' in demo
    assert '故障码是测试输入' in demo
    assert '仍需人工' in demo


def test_it_starts_with_the_preflight(demo):
    # The preflight exists so a missing saved AI run is discovered before an audience,
    # not during the walkthrough.
    assert 'demo_preflight.py' in demo
    assert (ROOT / 'scripts/demo_preflight.py').is_file()
    # And it must appear before the replay step it protects.
    assert demo.index('demo_preflight.py') < demo.index('真实 AI 回放')


def test_it_is_short_enough_to_follow(demo):
    assert len(demo.split('\n')) <= 135, 'a walkthrough nobody finishes is not a walkthrough'


def test_the_hand_loaded_extension_step_admits_it_cannot_be_automated(demo):
    # The reviewer must not think they missed a command that would load it for them.
    assert 'chrome://extensions' in demo
    assert '只能手动' in demo


def test_the_grounding_script_it_names_is_the_one_that_exists(demo):
    script = ROOT / 'scripts/evaluate_ai_grounding.py'
    assert script.is_file()
    assert 'evaluate_ai_grounding.py' in demo
    # Its own output must still state the boundary the walkthrough repeats.
    source = script.read_text(encoding='utf-8')
    assert 'not diagnostic accuracy' in source or 'accuracy' in source
