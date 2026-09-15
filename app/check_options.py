"""Source-backed check choices. The model selects IDs, never rewrites procedures."""
import hashlib


def build_check_options(evidence: dict, language: str = 'zh') -> list[dict]:
    result = []
    def add(key, zh, en, refs, provenance='application_rule', document='机联智检数据核验规则 v1'):
        result.append({'check_id': key, 'text': zh if language == 'zh' else en,
            'evidence_ids': refs, 'provenance': provenance, 'source_document': document,
            'limitation': '资料与适用性需核实；不是制造商认证的维修结论。' if language == 'zh' else 'Verify source and applicability; not a manufacturer-certified repair conclusion.'})
    for ref, item in evidence.items():
        if ref=='operator:manual-fault':
            add('check:manual-fault',
                '核对设备型号、协议版本及仪表显示的完整代码，并记录出现时间与是否仍在显示；代码定义不能代替维修手册或确认零件损坏。',
                'Verify the equipment model, protocol version and complete displayed code; record when it appeared and whether it is still displayed. A code definition is not a service procedure or proof of component damage.',
                [ref])
        elif ref=='prediction:cooling':
            add('check:cooling-source',
                '核对模拟片段、回放时点和温度传感器记录；实机应用前补充适用机型的热管理限值、冷却系统手册及标注数据。预警不能直接支持换件。',
                'Verify the synthetic episode, cutoff and temperature records. Obtain applicable thermal limits, cooling-system documentation and labelled real data before field use. A warning does not justify replacing parts.',
                [ref], 'application_rule', '机联智检冷却预警实验 v1')
        elif ref.endswith(':snapshot'):
            synthetic = item.get('source') in {'mock', 'imported_synthetic'}
            add('check:snapshot',
                '核对模拟数据的回放时点与记录时间；结论仅适用于该演示片段。' if synthetic else '核对最后上报时间与现场记录，确认缓存数据能否代表设备当前状态。',
                'Verify replay time and sample timestamps; conclusions apply only to this synthetic segment.' if synthetic else 'Compare last reported timestamps with site records before interpreting the cache as current machine state.', [ref])
        elif ref.endswith(':faults'):
            add('check:faults', '核对故障码、事件时间、状态及数据来源；不能把重复记录直接当作多次独立故障。',
                'Verify fault codes, timestamps, status and provenance; duplicate records do not establish independent failures.', [ref])
        elif ref.endswith(':trends'):
            if item.get('operating_hours_delta') is None or item.get('idle_share') is None or item.get('excluded_intervals', 0):
                add('check:trend-coverage', '补充并核对工时、怠速计数的时间戳与连续性；排除重置和冲突区间，满足有效运行时长后再计算窗口指标。',
                    'Obtain and verify timestamped operating and idle counters. Exclude resets and conflicts; compute window metrics only with sufficient valid runtime.', [ref])
        elif ref.endswith(':parts') and not item.get('candidates'):
            add('check:catalog-gap', '补充对应机型、序列号适用范围及故障码的备件目录或维修资料；无匹配结果不支持指定更换零件。',
                'Obtain parts or service documentation for the model, serial applicability and fault code. No match supports no specific replacement.', [ref])
        elif ref.startswith('catalog:'):
            for index, text in enumerate(item.get('checks', [])[:3]):
                key = hashlib.sha256((ref + ':' + str(index)).encode()).hexdigest()[:16]
                add('check:catalog:' + key, text, text, [ref], item.get('provenance', 'user_supplied'),
                    ' / '.join(str(item.get(k, '')) for k in ('source_document', 'source_page', 'revision')))
    return result[:64]
