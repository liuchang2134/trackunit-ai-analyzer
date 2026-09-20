"""Check that a demonstration will actually work before it starts.

Running the walkthrough only to discover the service is down, or that no saved AI run
exists to replay, wastes the reviewer's time in front of an audience. This prints a
readiness report and exits non-zero when something the walkthrough depends on is
missing.

Read-only: it queries the local service and reads local records. It calls no model and
changes nothing.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/demo_preflight.py
    .\\.tmp\\venv\\Scripts\\python.exe scripts/demo_preflight.py --origin http://127.0.0.1:8890
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_ORIGIN = 'http://127.0.0.1:8890'
HISTORY = ROOT / 'data/local/investigations'


def fetch(origin: str, path: str, timeout: float = 6.0):
    request = urllib.request.Request(origin + path, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def count_replayable() -> tuple[int, int, int]:
    """Saved records, how many contain real model decisions, and how many are unreadable.

    A file that cannot be read is counted separately rather than added to the total: an
    unreadable record is not a record the walkthrough can show, and including it would
    overstate how much history exists.
    """
    total = replayable = unreadable = 0
    for path in HISTORY.glob('*.json'):
        try:
            # Keep the raw value: `value or {}` would turn a missing report into an empty
            # dict, and the isinstance guard below would then accept it as a record.
            report = json.loads(path.read_text(encoding='utf-8')).get('report')
        except (OSError, ValueError):
            unreadable += 1
            continue
        if not isinstance(report, dict) or not report:
            unreadable += 1
            continue
        total += 1
        if int(report.get('model_decisions') or 0) >= 1:
            replayable += 1
    return total, replayable, unreadable


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default=DEFAULT_ORIGIN)
    args = parser.parse_args(argv)

    problems: list[str] = []
    print('演示前检查')
    print(f'  服务地址: {args.origin}')

    # Step 0–1: the service answers and offers devices to select.
    try:
        runtime = fetch(args.origin, '/assistant/runtime')
        print(f"  服务状态: 运行中，构建 {runtime.get('backend_build')}")
        provider = f"{runtime.get('provider')}/{runtime.get('model')}"
        print(f"  AI 配置 : {provider}")
        if runtime.get('provider') in (None, '', 'none'):
            problems.append('未配置 AI 提供方；第 7 步现场分析不可用（前六步不受影响）')
    except (urllib.error.URLError, OSError, ValueError) as error:
        problems.append(f'服务未响应（{error}）；请先运行 start_local.cmd --port 8890')
        runtime = {}

    try:
        index = fetch(args.origin, '/assistant/device-index')
        devices = index.get('devices') or []
        print(f"  可选设备: {len(devices)} 台（数据来源 {index.get('data_source')}）")
        if not devices:
            problems.append('没有可选设备；第 1 步设备自动关联无法演示')
        if index.get('data_source') == 'mock':
            print('           注意：当前为模拟数据源，讲解时应说明这一点')
    except (urllib.error.URLError, OSError, ValueError) as error:
        problems.append(f'设备索引不可用（{error}）；第 1 步无法演示')

    # The walkthrough needs a machine that can reach the manual step. A real fleet has no
    # broken machines and the other mock machines are not the model the excerpts cover, so
    # this scenario is what keeps the fault step from being empty.
    try:
        from scripts.prepare_demo_scenario import DEMO_MACHINE_ID, DEMO_MODEL, scenario_present
        state = scenario_present()
        print(f'  演示场景: {DEMO_MACHINE_ID} · {DEMO_MODEL}')
        for label, key, hint in (
            ('设备', 'machine', '第 1 步无法选中演示设备'),
            ('遥测', 'telemetry', '趋势图为空'),
            ('故障事件', 'fault', '第 2 步没有故障码可读'),
            ('手册摘录', 'manual_published', 'AI 无法给出手册页码'),
        ):
            ready = state.get(key)
            print(f"           {'就绪' if ready else '缺失'}: {label}")
            if not ready:
                problems.append(f'演示场景的{label}缺失（{hint}）；运行 scripts/prepare_demo_scenario.py')
    except ImportError as error:
        problems.append(f'无法读取演示场景：{error}')

    # The replay tab needs at least one run that really called a model.
    total, replayable, unreadable = count_replayable()
    print(f'  本机记录: {total} 条，其中真的跑过模型 {replayable} 条'
          + (f'（另有 {unreadable} 条无法读取，未计入）' if unreadable else ''))
    if replayable == 0:
        problems.append('没有含模型决策的记录；第 2 步真实 AI 回放与第 3 步证据包无法演示')
    else:
        print(f"           回放下拉框会显示 {replayable} 条（其余 {total - replayable} 条是程序输出，不展示）")

    # Step 4–5: the scripts the walkthrough asks the reviewer to run.
    for name in ('scripts/evaluate_ai_grounding.py', 'scripts/xgss_marking_probe.mjs',
                 'scripts/extension_probe.mjs'):
        exists = (ROOT / name).is_file()
        print(f"  {'就绪' if exists else '缺失'}: {name}")
        if not exists:
            problems.append(f'{name} 不存在；演示路径会引用到它')

    certificate = ROOT / '.tmp/fixture-cert/cert.pem'
    if certificate.is_file():
        print('  就绪: 图册夹具证书（第 5 步会用；缺失时脚本会自动生成）')
    else:
        print('  提示: 图册夹具证书尚未生成，第 5 步首次运行时会自动生成')

    print()
    if problems:
        print('发现以下问题：')
        for item in problems:
            print(f'  - {item}')
        return 1
    print('全部就绪，可以开始演示。注意：第 6 步加载插件需要手动操作，第 7 步现场分析需要密钥并产生费用。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
