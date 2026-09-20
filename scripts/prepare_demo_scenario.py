"""Prepare a self-contained demonstration scenario for the three-step flow.

The problem this solves is structural. The flow is identity -> telemetry -> fault code ->
manual reasoning -> catalog marking, and a real Trackunit fleet has no broken machines, so
the fault step has nothing to read and a live walkthrough stalls at step two. The
alternative — injecting a fault into a real machine's records — would be inventing data
about someone's equipment.

So the demonstration ships its own machine, and this script writes it into the mock data
source the app already reads (`app/mock_data/`), which is tracked by Git. That is what
makes the scenario distributable: a machine with no private material and no API key can
still run the whole flow.

What is real in the scenario and what is not:

  machine identity  synthetic   id prefixed DEMO-, serial prefixed SIM-
  telemetry         synthetic   fixed values, so two runs produce the same scenario
  fault event       synthetic   text says so, and the record carries a scenario marker
  manual excerpts   real        the manufacturer's own wording and page numbers

The manual excerpts are the part a reviewer can check against the real document, which is
why they are the part left alone.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/prepare_demo_scenario.py
    .\\.tmp\\venv\\Scripts\\python.exe scripts/prepare_demo_scenario.py --check
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEMO_DIR = ROOT / 'app/demo_data'
MACHINES = DEMO_DIR / 'machines.json'
TELEMETRY = DEMO_DIR / 'telemetry_snapshots.json'
FAULTS = DEMO_DIR / 'fault_codes.json'

# The manual knowledge covers XE55U and E4030 only, so the scenario uses that model: any
# other one would demonstrate the empty-answer path instead of the reasoning path.
DEMO_MACHINE_ID = 'DEMO-XE55U-001'
DEMO_SERIAL = 'SIM-DEMO-XE55U-001'
DEMO_MODEL = 'XE55U'
DEMO_FAULT_CODE = 'E4030'

# Private by default (data/local/ is gitignored). A distributable copy lives under
# data/demo/ so the scenario works without private material; redistribution of these
# excerpts was confirmed by the project owner.
MANUAL_SOURCE = ROOT / 'data/local/manual-knowledge/xe55u.json'
MANUAL_PUBLIC = ROOT / 'data/demo/manual-knowledge/xe55u.json'
SCENARIO_NOTE = ROOT / 'data/demo/SCENARIO.md'

SCENARIO_MARKER = 'synthetic_scenario'


def _iso(offset_minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)).strftime('%Y-%m-%dT%H:%M:%SZ')


def _read(path: Path) -> list:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')


def _without(rows: list, key: str, value: str) -> list:
    """Drop any previous copy so re-running replaces rather than duplicates."""
    return [row for row in rows if row.get(key) != value]


def machine_row() -> dict:
    # Model field names, not the camelCase the normalizer maps: these files are read
    # straight into the pydantic models, so a second conversion path would only be a place
    # for the two to drift apart.
    return {
        'machine_id': DEMO_MACHINE_ID,
        'trackunit_asset_id': DEMO_MACHINE_ID,
        'equipment_id': DEMO_SERIAL,
        'serial_number': DEMO_SERIAL,
        'model': DEMO_MODEL,
        'machine_type': 'excavator',
        'customer': '演示场景（合成设备）',
        'location': '演示场地',
        'last_seen_at': _iso(6),
    }


def telemetry_rows() -> list[dict]:
    """A flat, plausible history. Fixed values, so the scenario is reproducible."""
    rows = []
    hours = 1240.0
    idle = 348.0
    for index in range(12):
        hours += 0.45
        idle += 0.12
        rows.append({
            'machine_id': DEMO_MACHINE_ID,
            'trackunit_asset_id': DEMO_MACHINE_ID,
            'equipment_id': DEMO_SERIAL,
            'operating_hours': round(hours, 2),
            'idle_hours': round(idle, 2),
            'fuel_remaining_percent': round(72.0 - index * 1.6, 1),
            'engine_status': 'running' if index % 4 else 'stopped',
            'latitude': round(34.2712 + index * 0.0001, 6),
            'longitude': round(117.1832 + index * 0.0001, 6),
            'recorded_at': _iso((12 - index) * 10),
            'raw_payload': {'scenario': SCENARIO_MARKER},
        })
    return rows


def fault_row() -> dict:
    return {
        'machine_id': DEMO_MACHINE_ID,
        'trackunit_asset_id': DEMO_MACHINE_ID,
        'equipment_id': DEMO_SERIAL,
        'spn': 639,
        'fmi': 9,
        'fault_code': DEMO_FAULT_CODE,
        'description': 'J1939 总线故障（合成演示事件，非平台上报）',
        'severity': 'medium',
        'occurred_at': _iso(45),
        'status': 'open',
        # The marker travels with the record, so anything reading it can tell this was
        # generated for the walkthrough without trusting a caption on a slide.
        'raw_payload': {'scenario': SCENARIO_MARKER, 'not_a_trackunit_report': True},
    }


def publish_manual() -> tuple[bool, str]:
    if not MANUAL_SOURCE.is_file():
        return False, f'未找到私有手册 {MANUAL_SOURCE.relative_to(ROOT)}'
    MANUAL_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(MANUAL_SOURCE, MANUAL_PUBLIC)
    return True, str(MANUAL_PUBLIC.relative_to(ROOT))


def write_scenario_note(manual_published: bool, manual_detail: str) -> None:
    note = f"""# 演示场景

由 `scripts/prepare_demo_scenario.py` 生成，写入 `app/demo_data/`（随 Git 分发）。
不依赖私有资料、外部接口或 API 密钥。

## 场景内容

| 项 | 值 | 来源 |
|---|---|---|
| 设备 | `{DEMO_MACHINE_ID}` · {DEMO_MODEL} | **合成**（id 前缀 DEMO-） |
| 序列号 | `{DEMO_SERIAL}` | **合成**（前缀 SIM-） |
| 遥测 | 12 条，固定值，两次运行一致 | **合成** |
| 故障事件 | `{DEMO_FAULT_CODE}` | **合成**：事件文本与 `scenario` 字段均标明 |
| 手册摘录 | {DEMO_MODEL} 第 286／287 页 | **真实**：原厂手册原文与页码 |

## 为什么需要它

三步链是「设备身份 → 遥测 → 故障码 → 手册推理 → 图册标注」。真实车队里没有故障车，
故障这一步在真机上看不到数据；而 mock 数据源里的 5 台设备都不是 {DEMO_MODEL}，
手册查询会返回空。所以演示自带一台 {DEMO_MODEL} 与一个故障事件。

**没有触碰任何真实设备。** 演示设备是独立的一台，id 与真机无关。

## 唯一"真"的一层

手册摘录是原厂文档的原文与页码。AI 给出的页码可以对着真实 PDF 核，这是场景里唯一
需要外部核对的证据。

## 启用

在 `.env` 里设：

```
DATA_SOURCE=demo
```

然后重启后端。`demo` 是一个独立数据源（`app/demo_data/`），**不是**往 mock 车队里加设备：
mock 是离线演示和多个测试共用的夹具，往里加第二台 {DEMO_MODEL} 会让按机型查找的设备
变得有歧义。切回 `DATA_SOURCE=mock` 即可回到原来的 5 台模拟设备。

## 手册摘录

{manual_detail if manual_published else f'**未复制**：{manual_detail}，演示的手册引用将不可用。'}

## 移除

删除 `app/demo_data/` 整个目录，并把 `DATA_SOURCE` 切回 `mock`。本脚本重复运行是幂等的，
不会产生重复设备。
"""
    SCENARIO_NOTE.parent.mkdir(parents=True, exist_ok=True)
    SCENARIO_NOTE.write_text(note, encoding='utf-8')


def scenario_present() -> dict:
    machines = _read(MACHINES)
    telemetry = _read(TELEMETRY)
    faults = _read(FAULTS)
    return {
        'machine': any(row.get('machine_id') == DEMO_MACHINE_ID for row in machines),
        'telemetry': any(row.get('machine_id') == DEMO_MACHINE_ID for row in telemetry),
        'fault': any(row.get('machine_id') == DEMO_MACHINE_ID for row in faults),
        'manual_published': MANUAL_PUBLIC.is_file(),
    }


def prepare() -> int:
    # Only this machine's rows are replaced; every other machine is left exactly as it was.
    _write(MACHINES, _without(_read(MACHINES), 'machine_id', DEMO_MACHINE_ID) + [machine_row()])
    _write(TELEMETRY, _without(_read(TELEMETRY), 'machine_id', DEMO_MACHINE_ID) + telemetry_rows())
    _write(FAULTS, _without(_read(FAULTS), 'machine_id', DEMO_MACHINE_ID) + [fault_row()])
    published, detail = publish_manual()
    write_scenario_note(published, detail)
    state = scenario_present()

    print('演示场景已就绪')
    print(f"  设备    {DEMO_MACHINE_ID} · {DEMO_MODEL}   {'OK' if state['machine'] else '缺失'}")
    print(f"  遥测    {len(telemetry_rows())} 条   {'OK' if state['telemetry'] else '缺失'}")
    print(f"  故障    {DEMO_FAULT_CODE}（合成场景，非平台上报）   {'OK' if state['fault'] else '缺失'}")
    print(f"  手册    {detail}{'' if published else '（手册引用将不可用）'}")
    print(f"  说明    {SCENARIO_NOTE.relative_to(ROOT)}")
    return 0 if all(state.values()) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='report what is present and exit')
    args = parser.parse_args(argv)
    if args.check:
        state = scenario_present()
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0 if all(state.values()) else 1
    return prepare()


if __name__ == '__main__':
    raise SystemExit(main())
