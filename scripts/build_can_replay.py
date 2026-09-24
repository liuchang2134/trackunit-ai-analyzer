"""Build private, local-only replay data from the previously decoded CAN archive.

Usage: python scripts/build_can_replay.py PATH_TO_CAN_MATERIALS
No network requests. The output lives under gitignored data/local/.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    92: ('load', '发动机负载', '%', 2, 1, 1, 0),
    100: ('oil', '机油压力', 'kPa', 3, 1, 4, 0),
    110: ('coolant', '冷却液温度', '°C', 0, 1, 1, -40),
    168: ('voltage', '电源电压', 'V', 4, 2, .05, 0),
    183: ('fuel', '瞬时油耗', 'L/h', 0, 2, .05, 0),
    190: ('rpm', '发动机转速', 'rpm', 3, 2, .125, 0),
    247: ('hours', '累计工时', 'h', 0, 4, .05, 0),
}


def build(source: Path, destination: Path):
    meta = json.loads((source / 'xc948u_reference_decode.json').read_text(encoding='utf-8'))
    capture = next((source / 'extracted').rglob(meta['source_file']))
    inventory = json.loads((source / 'trace_inventory.json').read_text(encoding='utf-8'))
    trace = next(item for item in inventory if item['file'] == capture.name)
    with (source / 'xc948u_reference_telemetry_1s.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if r['source_address_hex'] == '00' and int(r['spn']) in FIELDS]
    wanted = {int(row['first_line']) for row in rows}
    frames = {}
    with capture.open(encoding='utf-8', errors='strict') as handle:
        for line_number, line in enumerate(handle, 1):
            if line_number in wanted:
                cells = line.split()
                assert cells[3:5] == ['Rx', 'd']
                frames[line_number] = (float(cells[0]), cells[2].rstrip('x').upper(), bytes.fromhex(' '.join(cells[6:6 + int(cells[5])])))
    signals = []
    for spn, (key, name, unit, start, size, factor, offset) in FIELDS.items():
        definition = next(r for r in meta['telemetry_summary'] if r['spn'] == spn and r['source_address_hex'] == '00')
        points = []
        for row in rows:
            if int(row['spn']) != spn:
                continue
            number = int(row['first_line'])
            at, can_id, data = frames[number]
            assert len(data) >= start + size
            raw = int.from_bytes(data[start:start + size], 'little')
            value = round(raw * factor + offset, 4) if raw < (0xfb << ((size - 1) * 8)) else None
            # first_line is the FIRST frame in the second, not the CSV's last value.
            points.append({'t': at, 'value': value, 'line': number, 'raw': data.hex(' ').upper(), 'can_id': can_id,
                           'count': int(row['valid_count']), 'min': float(row['min']) if row['min'] else None,
                           'max': float(row['max']) if row['max'] else None})
        signals.append({'key': key, 'name': name, 'unit': unit, 'spn': spn, 'pgn': definition['pgn'],
                        'reference_row': definition['reference_row'], 'byte_start': start + 1, 'byte_length': size,
                        'factor': factor, 'offset': offset, 'points': points})
    digest = hashlib.sha256()
    with capture.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    result = {'scenario': 'recorded', 'source_kind': 'real_capture', 'model': 'XC948U', 'vin': None,
              'capture_id': 'XC948U-20260916-CAN05', 'capture_date': '2026-09-16', 'duration': trace['last_frame_s'],
              'source_file': capture.name, 'sha256': digest.hexdigest(), 'frame_count': trace['frame_count'],
              'reference_workbook': meta['reference_workbook'], 'signals': signals,
              'diagnostics': meta['dm1_payload_variants'], 'unassembled_dm1': meta['unassembled_dm1_tp_announcements'],
              'sampling': '每秒首帧；时间为采集起点的相对秒数；未采样不补零。',
              'source_note': '仓库启停采集；来信描述无仪表报警。车型来自源邮件，VIN 与 Trackunit 资产尚未核对。'}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'output': str(destination), 'signals': len(signals), 'points': sum(len(s['points']) for s in signals), 'sha256': digest.hexdigest()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/local/can-demo/replay.json')
    args = parser.parse_args()
    build(args.source, args.output)
