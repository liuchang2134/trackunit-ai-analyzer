"""The preflight must fail loudly when a demonstration would not work.

Its whole purpose is to catch a broken setup before an audience sees it, so a check
that always reports "ready" is worse than no check. These tests drive it with a stubbed
service and stubbed records, and assert both the ready path and each failure path.
"""
import json
import urllib.error

import pytest

from scripts import demo_preflight


def record(directory, name, *, decisions):
    report = {'machine_id': 'M-1', 'model_decisions': decisions, 'status': 'completed'}
    (directory / f'{name}.json').write_text(
        json.dumps({'schema_version': 1, 'request': {'machine_id': 'M-1'}, 'report': report}),
        encoding='utf-8')


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    history = tmp_path / 'investigations'
    history.mkdir()
    # Only the records are redirected. ROOT is left alone because the script also checks
    # that the project's own scripts exist, and that check is part of what is being tested.
    monkeypatch.setattr(demo_preflight, 'HISTORY', history)
    return history


def stub_service(monkeypatch, *, runtime=None, devices=None, runtime_error=None, index_error=None):
    def fake_fetch(origin, path, timeout=6.0):
        if path == '/assistant/runtime':
            if runtime_error:
                raise urllib.error.URLError(runtime_error)
            return runtime if runtime is not None else {'backend_build': 'test-build',
                                                        'provider': 'deepseek', 'model': 'deepseek-flash'}
        if path == '/assistant/index-nonexistent':
            raise AssertionError('unexpected path')
        if path == '/assistant/device-index':
            if index_error:
                raise urllib.error.URLError(index_error)
            return devices if devices is not None else {'devices': [{'id': 'a'}], 'data_source': 'mock'}
        raise AssertionError(f'unexpected path {path}')
    monkeypatch.setattr(demo_preflight, 'fetch', fake_fetch)


def test_a_ready_setup_exits_zero(workspace, monkeypatch, capsys):
    record(workspace, 'ai1', decisions=2)
    stub_service(monkeypatch)
    assert demo_preflight.main([]) == 0
    out = capsys.readouterr().out
    assert '全部就绪' in out
    assert '真的跑过模型 1 条' in out


def test_a_dead_service_is_reported_not_ignored(workspace, monkeypatch, capsys):
    record(workspace, 'ai1', decisions=1)
    stub_service(monkeypatch, runtime_error='connection refused', index_error='connection refused')
    assert demo_preflight.main([]) == 1
    out = capsys.readouterr().out
    assert '服务未响应' in out
    assert 'start_local.cmd' in out, 'the report must say how to fix it'


def test_no_saved_ai_run_blocks_the_replay_step(workspace, monkeypatch, capsys):
    # Program-only records cannot be replayed, so this must fail rather than pass.
    record(workspace, 'plain1', decisions=0)
    record(workspace, 'plain2', decisions=0)
    stub_service(monkeypatch)
    assert demo_preflight.main([]) == 1
    out = capsys.readouterr().out
    assert '第 2 步' in out and '无法演示' in out
    assert '真的跑过模型 0 条' in out


def test_no_devices_blocks_the_first_step(workspace, monkeypatch, capsys):
    record(workspace, 'ai1', decisions=1)
    stub_service(monkeypatch, devices={'devices': [], 'data_source': 'mock'})
    assert demo_preflight.main([]) == 1
    assert '第 1 步' in capsys.readouterr().out


def test_a_mock_data_source_is_flagged_for_the_narration(workspace, monkeypatch, capsys):
    record(workspace, 'ai1', decisions=1)
    stub_service(monkeypatch, devices={'devices': [{'id': 'a'}], 'data_source': 'mock'})
    assert demo_preflight.main([]) == 0
    assert '模拟数据源' in capsys.readouterr().out


def test_a_missing_provider_is_reported_without_blocking_the_offline_steps(workspace, monkeypatch, capsys):
    record(workspace, 'ai1', decisions=1)
    stub_service(monkeypatch, runtime={'backend_build': 'b', 'provider': 'none', 'model': ''})
    # Steps 1-6 are offline, so this must not stop the walkthrough.
    assert demo_preflight.main([]) == 1
    out = capsys.readouterr().out
    assert '未配置 AI 提供方' in out
    assert '前六步不受影响' in out


def test_the_counting_separates_real_runs_from_program_output(workspace):
    record(workspace, 'ai1', decisions=3)
    record(workspace, 'ai2', decisions=1)
    record(workspace, 'plain', decisions=0)
    total, replayable, unreadable = demo_preflight.count_replayable()
    assert (total, replayable, unreadable) == (3, 2, 0)


def test_unreadable_records_are_skipped_rather_than_counted(workspace):
    record(workspace, 'ai1', decisions=1)
    (workspace / 'broken.json').write_text('{not json', encoding='utf-8')
    (workspace / 'shapeless.json').write_text(json.dumps({'no': 'report'}), encoding='utf-8')
    total, replayable, unreadable = demo_preflight.count_replayable()
    assert (total, replayable) == (1, 1), 'a file that cannot be read must not inflate the total'
    assert unreadable == 2, 'unreadable files are reported separately, not as history'


def test_the_scripts_it_checks_are_the_ones_the_walkthrough_names():
    from pathlib import Path
    root = Path(demo_preflight.__file__).resolve().parents[1]
    walkthrough = (root / 'docs/演示路径.md').read_text(encoding='utf-8')
    for name in ('evaluate_ai_grounding.py', 'xgss_marking_probe.mjs', 'extension_probe.mjs'):
        assert name in walkthrough, f'the walkthrough must mention {name}'
        assert (root / 'scripts' / name).is_file(), f'{name} is missing'
