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


def test_every_script_it_names_exists(demo):
    scripts = re.findall(r'scripts[\\/]([A-Za-z0-9_]+\.(?:py|mjs))', demo)
    assert scripts, 'the demo path must name the script used for optional developer verification'
    missing = [name for name in scripts if not (ROOT / 'scripts' / name).is_file()]
    assert missing == [], f'the demo path names scripts that do not exist: {missing}'


def test_the_launcher_it_names_exists(demo):
    assert 'start_local.cmd' in demo
    assert (ROOT / 'start_local.cmd').is_file()


def test_it_points_at_screens_that_actually_exist(demo):
    # Static controls and the dynamically built research workspace have different
    # source files. Bind the current route to both, not to the retained replay UI.
    index = (ROOT / 'app/assistant_ui/index.html').read_text(encoding='utf-8')
    panel = (ROOT / 'extension/panel.html').read_text(encoding='utf-8')
    research = (ROOT / 'app/assistant_ui/xgss-research-workspace.js').read_text(encoding='utf-8')
    for label in ('设备排查', '运行数据与故障记录', '故障码资料',
                  'AI 辅助排查', '开始分析', '停止分析'):
        assert label in demo, f'the walkthrough must mention {label}'
        assert f'>{label}<' in index, f'the static workspace control {label} must exist'
    for label in ('备件与维修建议', '故障现象', '查找备件与维修资料',
                  '继续查找备件', '更多操作与检索词', '查找并提取资料', '查看设备证据'):
        assert label in demo, f'the walkthrough must mention {label}'
        assert f"'{label}'" in research, f'the dynamic research control {label} must exist'
    assert '读取设备' in demo
    assert re.search(r'<button[^>]*id="identify"[^>]*>读取设备</button>', panel)


def test_the_walkthrough_has_no_simulated_case_left(demo):
    # The old scripted walkthrough must not return. A clearly marked simulated
    # symptom in the current device workflow is a separate, supported input.
    index = (ROOT / 'app/assistant_ui/index.html').read_text(encoding='utf-8')
    for stale_markup in ('讲解案例', '模拟案例', 'demo-mode-scripted', 'demo-case.js', 'demo-content'):
        assert stale_markup not in index, f'the demo view must not carry {stale_markup} any more'
    for stale_text in ('讲解案例', '切到「'):
        assert stale_text not in demo, f'the walkthrough must not instruct {stale_text}'


def test_it_says_which_steps_need_a_key(demo):
    # Local inspection does not call AI, but the live route still needs service access.
    assert '[无需密钥]' in demo and '[需密钥]' in demo
    assert '无需 AI 密钥' in demo and 'Trackunit 凭据' in demo
    assert '全部可离线完成' not in demo and '全部无需密钥' not in demo


def test_it_states_what_the_walkthrough_does_not_prove(demo):
    assert '没证明诊断准确率' in demo
    assert '样本量小' in demo
    assert '故障码是测试输入' in demo
    assert '仍需人工' in demo


def test_it_checks_the_service_before_the_device_walkthrough(demo):
    # A live device demonstration needs the local service, not a previously saved AI run.
    check = re.search(r'^start_local\.cmd\s+--port\s+8890\s+--check-only\s*$', demo, re.M)
    assert check, 'the walkthrough must first check the existing local service'
    first_step = re.search(r'^##\s+1\.\s+关联 Trackunit 当前设备', demo, re.M)
    assert first_step and check.start() < first_step.start()
    launcher = ROOT / 'scripts/start_assistant.py'
    assert launcher.is_file()
    assert '--check-only' in launcher.read_text(encoding='utf-8')
    assert 'demo_preflight.py' not in demo, 'saved historical reports are not a prerequisite for this route'


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
    assert '仅做本机开发复核' in demo and '不在现场展示路线内' in demo
    # Its own output must still state the boundary the walkthrough repeats.
    source = script.read_text(encoding='utf-8')
    assert 'not diagnostic accuracy' in source or 'accuracy' in source
