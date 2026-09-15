"""Mechanism-based SYNTHETIC excavator data. Standard library only; no live APIs."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DT = 5
STEPS = 8 * 3600 // DT
SEED = 20260914
CLASSES = ['healthy', 'normal_shutdown', 'network_outage', 'terminal_power_loss',
           'fuel_sensor_freeze', 'cache_stale', 'cloud_batch_delay']
SOURCE = 'https://xcmg-usa.com/wp-content/uploads/2025/04/XCMG_Brochures_XE135U_0425_WEB.pdf'
PROFILE = {
    'name': 'SYNTHETIC diesel excavator, XE135U brochure envelope reference only',
    'brochure_version': '4.14-2025-01', 'source_url': SOURCE,
    'rated_power_kw': 90, 'maximum_torque_nm': 500, 'tank_l': 250,
    'idle_rpm_range': [950, 1100], 'max_travel_kmh': 4.7,
    'note': 'Brochure lists 2200 rpm and a conflicting 2100 rpm label; model caps at 2100, not a calibration.',
}
ASSUMPTIONS = {
    'not_measured': True, 'not_a_digital_twin': True,
    'physical_step_seconds': DT, 'nominal_cloud_sample_seconds': 60,
    'fuel_model': 'fuel_lph = 1.6 + shaft_power_kw * 0.245 / 0.835 while engine on; zero off',
    'fuel_parameters': '1.6 L/h parasitic/intercept, 0.245 kg/kWh slope, 0.835 kg/L diesel density: assumed, not OEM curve',
    'thermal_model': 'first-order relaxation to load-dependent targets; no cooling-failure model',
    'hydraulic_model': 'single equivalent circuit; output = 0.76 * (shaft - 4kW auxiliaries); Q=600P/p',
    'state_model': 'semi-Markov excavation cycle with assumed durations and soil/operator factors',
    'scope': 'one simulated fault at a time; no physical component failures or real SPN/FMI codes',
    'detailed_channels': 'rpm/pressure/flow/temperature are simulator channels, NOT guaranteed Trackunit account fields',
}
SPEC = {
    'dig': (10, 25, 0.70), 'loaded_swing': (5, 12, 0.46),
    'dump': (5, 10, 0.27), 'return_swing': (5, 12, 0.35),
    'idle': (30, 240, 0.07), 'travel': (30, 150, 0.48),
}
TRUTH_FIELDS = ['elapsed_s', 'timestamp', 'work_state', 'engine_on', 'engine_rpm',
                'shaft_kw', 'hydraulic_kw', 'hydraulic_pressure_bar', 'hydraulic_flow_lpm',
                'fuel_lph', 'fuel_l', 'fuel_burn_l', 'operating_hours', 'idle_hours',
                'coolant_c', 'hydraulic_oil_c', 'ambient_c', 'speed_kmh', 'x_m', 'y_m',
                'terminal_power', 'network_connected']
PUBLIC_FIELDS = ['elapsed_s', 'observed_at', 'recorded_at', 'fuel_sampled_at', 'machine_id',
                 'engine_status', 'operating_hours', 'idle_hours', 'fuel_percent',
                 'latitude', 'longitude', 'age_seconds', 'origin']


def iso(base, seconds):
    return (base + timedelta(seconds=seconds)).isoformat()


def simulate(seed, scenario, steps=STEPS):
    """Independent episode, interval-end samples; cloud queue uses sample time, never future truth."""
    assert scenario in CLASSES
    rng = random.Random(seed)
    link_rng = random.Random(seed + 314159)
    base = datetime(2026, 1, 1, 7, tzinfo=timezone.utc) + timedelta(days=rng.randrange(180))
    machine_id = 'SIM-' + hashlib.sha256(str(seed).encode()).hexdigest()[:12]
    ambient = rng.uniform(5, 35)
    soil_factor, operator_factor = rng.uniform(.85, 1.12), rng.uniform(.9, 1.1)
    fuel = initial_fuel = rng.uniform(190, 240)
    initial_hours = hours = rng.uniform(200, 5000)
    initial_idle = idle_hours = hours * rng.uniform(.1, .25)
    coolant = oil = ambient
    rpm, shaft, x, y, state, left = 0., 0., 0., 0., 'idle', 0
    direction = rng.uniform(-math.pi, math.pi)
    initial_warmup = rng.randrange(240, 601, DT)
    onset = rng.randrange(4800, 6601, DT)
    duration = rng.randrange(1200, 3601, DT)
    end = onset + duration
    cloud = cache = sensor_hold = None
    sensor_time = None
    queued, physical, observed, audit = [], [], [], []
    freeze_value = None
    previous_fuel = fuel
    last_cloud_received = None
    for i in range(steps):
        elapsed = (i + 1) * DT
        active = onset <= elapsed < end
        # Planned lunch, end-of-shift and deliberate shutdown are distinct from telematics loss.
        stopped = (14400 <= elapsed < 16200 or elapsed >= 28200 or
                   (scenario == 'normal_shutdown' and active))
        if stopped:
            state, left = 'off', 0
        elif elapsed <= initial_warmup or 16200 <= elapsed < 16380:
            state, left = 'warmup', 0
        else:
            left -= DT
            if left <= 0 or state in ('off', 'warmup'):
                if state == 'dig':
                    state = 'loaded_swing'
                elif state == 'loaded_swing':
                    state = 'dump'
                elif state == 'dump':
                    state = 'return_swing'
                elif state == 'return_swing':
                    state = rng.choices(['dig', 'idle', 'travel'], [.84, .13, .03])[0]
                else:
                    state = 'dig'
                lo, hi, _ = SPEC[state]
                left = max(DT, round(rng.uniform(lo, hi) / operator_factor / DT) * DT)
                if state == 'travel':
                    direction = math.atan2(-y, -x) + rng.uniform(-.5, .5) if math.hypot(x, y) > 100 else rng.uniform(-math.pi, math.pi)
        engine_on = state != 'off'
        if engine_on:
            target_rpm = rng.uniform(950, 1100) if state in ('idle', 'warmup') else rng.uniform(1650, 2050)
            rpm += (target_rpm - rpm) * .55
            fraction = .07 if state == 'warmup' else SPEC[state][2]
            target_kw = min(82, max(4.5, 90 * fraction * soil_factor * operator_factor * rng.uniform(.9, 1.1)))
            shaft += (target_kw - shaft) * .6
            shaft = min(shaft, .90 * 500 * rpm * 2 * math.pi / 60 / 1000)
        else:
            rpm = shaft = 0.
        hydraulic = max(0., shaft - 4) * .76 if state not in ('idle', 'warmup', 'off') else 0.
        pressure = min(280., max(30., 70 + hydraulic * 3)) if hydraulic else (20. if engine_on else 0.)
        flow = hydraulic * 600 / pressure if pressure else 0.
        fuel_rate = 1.6 + shaft * .245 / .835 if engine_on else 0.
        burn = fuel_rate * DT / 3600
        fuel -= burn
        hours += DT / 3600 if engine_on else 0
        idle_hours += DT / 3600 if state in ('idle', 'warmup') else 0
        coolant_target = ambient + 48 + 22 * shaft / 90 if engine_on else ambient
        oil_target = ambient + 15 + 42 * hydraulic / 65 if engine_on else ambient
        coolant += (coolant_target - coolant) * (1 - math.exp(-DT / (600 if engine_on else 1800)))
        oil += (oil_target - oil) * (1 - math.exp(-DT / (900 if engine_on else 2400)))
        speed = rng.uniform(1, 3) if state == 'travel' else 0.
        x += speed / 3.6 * DT * math.cos(direction)
        y += speed / 3.6 * DT * math.sin(direction)
        terminal = not (active and scenario == 'terminal_power_loss')
        network = not (active and scenario == 'network_outage')
        p = dict(zip(TRUTH_FIELDS, [elapsed, iso(base, elapsed), state, engine_on, rpm, shaft,
                   hydraulic, pressure, flow, fuel_rate, fuel, burn, hours, idle_hours, coolant, oil,
                   ambient, speed, x, y, terminal, network]))
        physical.append(p)
        assert abs(previous_fuel - fuel - burn) < 1e-9
        previous_fuel = fuel
        # Sensor re-samples each minute with quantization; sample timestamp refers to held fuel signal.
        if elapsed % 60 == 0 and terminal:
            if active and scenario == 'fuel_sensor_freeze':
                if freeze_value is None:
                    freeze_value = sensor_hold if sensor_hold is not None else round(fuel / 250 * 100, 1)
                sensor_hold = freeze_value
            else:
                sensor_hold = round(min(100, max(0, fuel / 250 * 100 + link_rng.gauss(0, .04))), 1)
                sensor_time = elapsed
                freeze_value = None
            payload = {'sample_s': elapsed, 'fuel_sample_s': sensor_time or elapsed,
                       'engine_status': 'running' if engine_on else 'stopped',
                       'operating_hours': round(hours, 4), 'idle_hours': round(idle_hours, 4),
                       'fuel_percent': sensor_hold,
                       'latitude': round(35 + y / 111320, 7),
                       'longitude': round(-95 + x / (111320 * math.cos(math.radians(35))), 7)}
            if network and link_rng.random() > .01:
                delay = (end - elapsed + link_rng.randrange(5, 31, 5)) if active and scenario == 'cloud_batch_delay' else link_rng.choice([5, 5, 10, 15])
                queued.append((elapsed + delay, payload))
        arrivals = [item for item in queued if item[0] <= elapsed]
        queued = [item for item in queued if item[0] > elapsed]
        for received, payload in sorted(arrivals, key=lambda item: (item[0], item[1]['sample_s'])):
            if cloud is None or payload['sample_s'] > cloud['sample_s']:
                cloud = payload
                last_cloud_received = received
        if not (active and scenario == 'cache_stale'):
            cache = cloud
        if elapsed % 60 == 0:
            row = {'elapsed_s': elapsed, 'observed_at': iso(base, elapsed), 'machine_id': machine_id,
                   'origin': 'synthetic', 'recorded_at': None, 'fuel_sampled_at': None,
                   'age_seconds': None, 'engine_status': None, 'operating_hours': None,
                   'idle_hours': None, 'fuel_percent': None, 'latitude': None, 'longitude': None}
            if cache:
                row.update({k: cache[k] for k in ('engine_status', 'operating_hours', 'idle_hours', 'fuel_percent', 'latitude', 'longitude')})
                row.update(recorded_at=iso(base, cache['sample_s']),
                           fuel_sampled_at=iso(base, cache['fuel_sample_s']),
                           age_seconds=elapsed-cache['sample_s'])
            observed.append(row)
            audit.append({'elapsed_s': elapsed, 'cloud_sample_s': cloud['sample_s'] if cloud else None,
                          'cloud_received_s': last_cloud_received,
                          'cache_sample_s': cache['sample_s'] if cache else None})
    decision_s = (onset + 600) // 60 * 60
    state_now = physical[decision_s // DT - 1]
    layer_now = next(a for a in audit if a['elapsed_s'] == decision_s)
    # All numbers are frozen at decision_s. Expose one action outcome at a time via a future backend.
    network_value = state_now['network_connected']
    power_value = state_now['terminal_power']
    actions = {
        'cloud_freshness': {'cost_units': 1, 'manual': False,
                            'result': {'sample_age_s': decision_s-layer_now['cloud_sample_s'] if layer_now['cloud_sample_s'] else None}},
        'terminal_power_inspection': {'cost_units': 5, 'manual': True, 'result': {'powered': power_value}},
        'network_inspection': {'cost_units': 5, 'manual': True, 'result': {'connected': network_value}},
        'local_engine_observation': {'cost_units': 5, 'manual': True, 'result': {'running': state_now['engine_on']}},
        'fuel_crosscheck': {'cost_units': 6, 'manual': True, 'result': {'independent_fuel_percent': round(state_now['fuel_l']/250*100, 1)}},
        'platform_ingestion_audit': {'cost_units': 2, 'manual': False, 'result': {'delayed_batch': scenario == 'cloud_batch_delay'}},
    }
    # Availability is independent of class. There may be insufficient evidence: no forced unique-answer claim.
    availability = random.Random(seed + 999999)
    for action in actions.values():
        action['available'] = availability.random() >= .2
        if not action['available']:
            action['result'] = None
        action['as_of_s'] = decision_s
    return {'machine_id': machine_id, 'seed': seed, 'scenario': scenario,
            'start_utc': base.isoformat(), 'onset_s': onset, 'end_s': end,
            'decision_s': decision_s, 'ambient_c': ambient,
            'initial_fuel_l': initial_fuel, 'initial_operating_hours': initial_hours,
            'initial_idle_hours': initial_idle, 'physical': physical, 'observations': observed,
            'layers': audit, 'actions': actions}


def validate(episode):
    prev = None
    total_burn = 0.
    engine_seconds = idle_seconds = 0
    for row in episode['physical']:
        assert 0 < row['fuel_l'] <= PROFILE['tank_l']
        assert 0 <= row['shaft_kw'] <= 90
        assert row['hydraulic_kw'] <= max(0, row['shaft_kw'] - 4) + 1e-8
        assert abs(row['hydraulic_kw'] - row['hydraulic_pressure_bar'] * row['hydraulic_flow_lpm'] / 600) < 1e-8
        assert row['speed_kmh'] <= PROFILE['max_travel_kmh']
        assert row['speed_kmh'] == 0 or row['work_state'] == 'travel'
        assert row['engine_on'] or (row['fuel_lph'] == 0 and row['engine_rpm'] == 0)
        if row['engine_rpm']:
            assert row['shaft_kw'] * 1000 / (row['engine_rpm'] * 2 * math.pi / 60) <= 500
        if prev:
            assert row['elapsed_s'] - prev['elapsed_s'] == DT
            assert abs(row['coolant_c'] - prev['coolant_c']) < 1
            assert abs(row['hydraulic_oil_c'] - prev['hydraulic_oil_c']) < 1
            distance = math.hypot(row['x_m']-prev['x_m'], row['y_m']-prev['y_m'])
            assert abs(distance - row['speed_kmh']/3.6*DT) < 1e-8
        engine_seconds += DT if row['engine_on'] else 0
        idle_seconds += DT if row['work_state'] in ('idle', 'warmup') else 0
        total_burn += row['fuel_burn_l']
        prev = row
    assert abs(episode['initial_fuel_l'] - prev['fuel_l'] - total_burn) < 1e-7
    assert abs(prev['operating_hours'] - episode['initial_operating_hours'] - engine_seconds/3600) < 1e-7
    assert abs(prev['idle_hours'] - episode['initial_idle_hours'] - idle_seconds/3600) < 1e-7
    for row, layer in zip(episode['observations'], episode['layers']):
        assert row['age_seconds'] is None or row['age_seconds'] >= 0
        if layer['cache_sample_s'] is not None:
            assert layer['cache_sample_s'] <= row['elapsed_s']
    return {'fuel_burn_l': round(total_burn, 3), 'engine_hours': round(engine_seconds/3600, 3),
            'idle_hours': round(idle_seconds/3600, 3), 'maximum_coolant_c': round(max(r['coolant_c'] for r in episode['physical']), 2)}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == '.gz':
        # Fixed gzip timestamp and no filename make bytes reproducible.
        with path.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as gz:
            with io.TextIOWrapper(gz, encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
    else:
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def generate(output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Output must be new or empty; refusing to overwrite an existing dataset.')
    write_json(output/'profile_and_assumptions.json', {'profile': PROFILE, 'assumptions': ASSUMPTIONS})
    assignments = []
    rng = random.Random(SEED)
    for split, count in [('train', 4), ('validation', 1), ('test', 1)]:
        classes = CLASSES * count
        rng.shuffle(classes)
        for scenario in classes:
            assignments.append((split, scenario, rng.randrange(10**8, 10**9)))
    inventory, checks = [], []
    for split, scenario, seed in assignments:
        ep = simulate(seed, scenario)
        report = validate(ep)
        eid = 'EP-' + hashlib.sha256(str(seed).encode()).hexdigest()[:12]
        public = output/'public'/split/eid
        private = output/'evaluator_only'/split/eid
        write_csv(public/'telemetry.csv.gz', PUBLIC_FIELDS, [r for r in ep['observations'] if r['elapsed_s'] <= ep['decision_s']])
        write_csv(private/'telemetry_replay.csv.gz', PUBLIC_FIELDS, ep['observations'])
        write_json(public/'episode.json', {'episode_id': eid, 'machine_id': ep['machine_id'],
                   'origin': 'synthetic', 'start_utc': ep['start_utc'], 'decision_s': ep['decision_s'],
                   'instruction': 'Telemetry is clipped at decision_s. Full replay and answers belong to evaluator_only, not model inputs.'})
        write_json(public/'action_catalog.json', {k:{a:v for a,v in value.items() if a in ('cost_units','manual')} for k,value in ep['actions'].items()})
        write_csv(private/'physical_truth.csv.gz', TRUTH_FIELDS, ep['physical'])
        write_csv(private/'layer_audit.csv.gz', list(ep['layers'][0]), ep['layers'])
        metadata = {k:v for k,v in ep.items() if k not in ('physical','observations','layers','actions')}
        write_json(private/'ground_truth.json', metadata)
        write_json(private/'action_oracle.json', ep['actions'])
        inventory.append({'episode_id': eid, 'split': split, 'machine_id': ep['machine_id'],
                          'scenario': scenario, **report})
        checks.append({'episode_id': eid, 'passed': True})
        if scenario == 'network_outage' and split == 'train' and not (output/'preview_telemetry.csv').exists():
            write_csv(output/'preview_telemetry.csv', PUBLIC_FIELDS, ep['observations'])
            write_csv(output/'preview_physical_truth.csv', TRUTH_FIELDS, ep['physical'])
    assert len({r['machine_id'] for r in inventory}) == len(inventory)
    write_json(output/'evaluator_only'/'inventory.json', inventory)
    write_json(output/'validation_report.json', {'origin':'synthetic', 'seed':SEED, 'episodes':len(inventory),
               'physical_rows':len(inventory)*STEPS, 'telemetry_rows':len(inventory)*480,
               'simulated_hours':len(inventory)*8,
               'split_counts':dict(Counter(r['split'] for r in inventory)),
               'class_counts':dict(Counter(r['scenario'] for r in inventory)), 'checks':checks,
               'meaning':'Physical/temporal invariants passed, NOT empirical fidelity or diagnostic accuracy.'})
    card = '''# 工程机械车联网合成数据集 v1

**性质：公开规格约束下的机制仿真，未用真机时间序列校准；不是现场采集数据，也不是已验证的数字孪生。**

## 数据规模

42 个独立虚拟设备班次，每班 8 小时；5 秒内部物理步长，1 分钟平台查询记录。
共 336 仿真设备小时、241,920 条内部物理记录、20,160 条平台观测。
28/7/7 个完整班次分为 train/validation/test。7 类各 6 班：正常运行、正常停机、断网、终端断电、油量信号冻结、缓存过期、云端批量延迟。
各类别均衡是评测设计，绝不是实际故障发生率。每台设备仅一个班次，不用于设备寿命建模。

## 工程依据与假设

参考 XE135U 北美 2025-04 官方手册 Version 4.14-2025-01：90 kW、最大扭矩 500 N·m、250 L 油箱、950–1100 rpm 怠速范围、最高行走速度 4.7 km/h。
参考来源见 profile_and_assumptions.json。该手册额定转速有 2100/2200 rpm 文本冲突，仿真上限取 2100，未将此解释为实机标定。
本产品称为通用柴油挖机仿真，不宣称复制该型号。没有复用电动小挖机 SOC 数据来生成柴油油耗。

作业顺序：暖机→挖掘→重载回转→卸料→空载回转，随机插入等车怠速和短途移动；午休停机和收工停机。
动作时长、土质/操作因子、燃油模型系数、温度时间常数、等效液压压力/效率均为显式仿真假设，不是实测分布或 OEM 控制策略。
燃油从逐步耗油积分扣减；发动机小时只在开机累计；怠速小时是其中子集。
压力×流量换算的液压功率不超过轴功率扣除辅助功率后的可用量；温度有热惯性；只有行走改变真实位置。
5 秒采样不足以研究发动机起动、CAN 电气瞬态、液压冲击或每个细小控制动作。
油耗模型为经验结构，不能替代发动机 BSFC 图；热模型不能预测过热故障；不模拟部件磨损和寿命。

## 链路与异常语义

物理真值与传感器值→终端采样→网络发送→云端入库→本地缓存→用户读取分层生成。
断网/终端断电不会自动停止发动机；恢复后恢复新采样，当前仿真未实现终端离线补传。
云端延迟会在恢复后批量到达，并保留原采样时间；旧包不得覆盖新值。
缓存过期时云端仍更新；冻结油量时其他字段继续更新。
正常停机保持终端在线是本版配置假设，实际终端休眠/断电逻辑需按现场配置扩展。
正常情况下也有 1% 独立报文丢失及 5–15 秒网络延迟；未声称代表 Trackunit 服务 SLA。
fuel_sampled_at 是模拟器扩展字段，Trackunit 真实接口未必提供。转速/液压/温度仅存内部真值，不默认平台可以取得。
未伪造真实 SPN/FMI 故障码，也没有给机械部件故障贴未经证实的标签。

## 文件与使用

- public/<split>/<episode>/telemetry.csv.gz：已裁切到诊断截点的平台可见时序；年龄均相对 observed_at 计算，禁止相对当前电脑时间计算。
- public/.../episode.json：仿真开始时间与诊断截点 decision_s。
- public/.../action_catalog.json：检查名称、成本单位和是否人工；成本是相对模拟单位，不是分钟或钱。
- evaluator_only/.../physical_truth.csv.gz：物理轨迹与状态，仅评测器/回放使用。
- evaluator_only/.../ground_truth.json：原因、注入窗口、随机种子，只给评测器。
- evaluator_only/.../action_oracle.json：检查结果固定在诊断截点，每次只返回请求的一个检查。20% 独立不可用概率；并不保证全部案例可唯一诊断。
- evaluator_only/.../layer_audit.csv.gz：云端/缓存时间审计。
- evaluator_only/.../telemetry_replay.csv.gz：完整班次平台记录，仅作评分后的恢复过程回放。
- preview_telemetry.csv：一个训练断网案例的完整平台观测，可直接查看。
- preview_physical_truth.csv：同一案例的完整物理轨迹，演示专用，不可输入诊断模型。
- validation_report.json：已运行的工程一致性检查结果。

**防止泄漏：**public 下平台输入已裁切 elapsed_s <= decision_s。preview 和 evaluator_only 文件包含未来或答案，只用于演示回放和评分。不能把 evaluator_only、preview、随机种子、原因、作业真值或全部检查结果放入模型输入。目录隔离不是访问控制，接入后端时必须落实。测试集与训练集来自相同生成机制：可以证明模拟域内对比，不证明现实泛化。

字段：elapsed_s 为班次开始后的秒数；recorded_at 为最新缓存遥测的原采样时间；fuel_sampled_at 为油量独立采样时间；operating_hours/idle_hours 为累计小时；fuel_percent 为0–100；经纬度以虚拟场地为中心；空字段表示没有数据，绝非零值。

## 复现与验收

在项目根目录运行：`python scripts/generate_diagnostic_dataset.py --output data/new_synthetic_run`。
不覆盖已有输出。仅使用 Python 标准库。代码内固定种子；完整文件 SHA-256 见 manifest.json。
验证燃油守恒、运行计时、扭矩/功率边界、液压功率、温度连续性、移动与速度一致、无未来数据及分组隔离。
尚未训练诊断模型、进行对照试验、或校准真实设备；没有宣称诊断准确率、节省时间或维修成本。

下一版应以同机型授权作业记录校准动作时长、油耗和热响应；用真实链路日志校准采样/延迟，并加入复合异常、终端休眠与未知原因场景。
'''
    (output/'README.md').write_text(card, encoding='utf-8')
    files = sorted(p for p in output.rglob('*') if p.is_file())
    write_json(output/'manifest.json', {str(p.relative_to(output)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    print(json.dumps({'output':str(output.resolve()),'episodes':len(inventory),'all_invariants_passed':True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='data/synthetic_diagnostics_v1')
    generate(parser.parse_args().output)
