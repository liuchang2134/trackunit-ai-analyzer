"""Separate catalog identity from fault-to-part evidence. No model/network calls."""
import re

VERSION = 'fault-causality-2'
INSTRUCTIONS = (
    '先独立解释当前选中的故障码含义与失效机理，再按最可能、最易核查的顺序给检查步骤；不要沿用旧 AI 的结论作为证据。'
    '通讯丢失/异常更新率表示报文或节点通信异常，不等于电源损坏。优先核对故障节点、总线线束/插接件、终端与网络配置；'
    '节点供电和接地是检查步骤，缺少独立供电异常证据时，不推荐蓄电池、电源继电器、保险盒、控制器或整机线束。'
    '电压偏低同样不能区分蓄电池、接触压降、接地或充电异常，单个故障码不能证明某个部件损坏。'
    '爆炸图只证明零件身份和图示位置，不能证明其属于某个 SPN/ECU 引脚或电气回路。不要声称图册未提供的回路连接。'
    'parts 最多三项，宁缺毋滥，不按图册顺序填满。每项 fault_relation 必须为 direct（直接相关待核查）、'
    'shared_cause（共同原因需独立证据）或 unmapped（未建立联系，应不选）。'
    'support=catalog_only 表示只有同机图册名称/系统关联，将作为优先核查对象而不是备件准备；'
    'support=manual_mapping 必须用 support_source_id 和完整 support_quote 引用适用手册中当前故障码与该部件的明确关联；'
    'support=component_observation 必须在 support_quote 逐字引用人工报告中已完成检查确认该具体部件异常的内容。'
    '待检查、如果损坏、询问、旧 AI 建议、故障码描述和同页相邻零件都不算已确认部件异常。'
    '没有上述依据，support 必须为 catalog_only，reason 只解释可能关联和仍需核对的回路，不能说已经适配故障点或应更换。'
    'replacement_condition 写实际检查怎样区分原因，不能只写检查确认后更换。不要仅凭关键字给全车电气部件列表。'
)
PLAN_INSTRUCTIONS = INSTRUCTIONS.split('parts 最多三项', 1)[0]

_COMM = re.compile(r'总线.{0,8}(?:故障|异常|通信|通讯)|(?:通信|通讯).{0,8}(?:故障|异常|丢失|中断|超时)|'
                   r'\b(?:communication (?:fault|failure|error|lost)|lost communication|abnormal update rate|bus off)\b|\bFMI\s*[:=/]?\s*9\b', re.I)
_POWER_PART = re.compile(r'蓄电池|电瓶|电源|总开关|保险|熔断|继电器|发电机|控制器|\b(?:battery|power supply|relay|fuse|alternator|ECU|controller)\b', re.I)
_POWER_OBSERVATION = re.compile(r'(?:实测|测得|已检查|已确认).{0,40}(?:供电|电压|蓄电池|电瓶|保险|熔断|接地).{0,20}(?:异常|不足|偏低|断路|熔断|损坏)|'
                                r'(?:供电|电压|蓄电池|电瓶|保险|接地).{0,20}(?:实测|测得|已确认).{0,20}(?:异常|偏低|不足|熔断|损坏)')
_COMPLETED = re.compile(r'已检查|检查确认|检测确认|实测|测得|已确认|发现.{0,8}(?:破损|烧蚀|断裂|泄漏|腐蚀|松脱)|\b(?:measured|confirmed|inspection found)\b', re.I)
_DAMAGE = re.compile(r'破损|烧蚀|断裂|泄漏|腐蚀|松脱|断路|短路|熔断|失效|损坏|\b(?:damaged|broken|burnt|corroded|failed)\b', re.I)
_HYPOTHETICAL = re.compile(r'如果|若|假如|是否|待(?:现场)?(?:检查|确认|核实)|未(?:检查|确认|发现)|没有|无.{0,4}(?:异常|损坏)|未见|需(?:要)?(?:检查|确认)|\b(?:if|not|whether|check for)\b', re.I)
_PAIR = re.compile(r'SPN\s*[:=]?\s*(\d+)\s*[/,，;；-]?\s*FMI\s*[:=]?\s*(\d+)', re.I)
_OEM = re.compile(r'\b[A-Z]{1,3}\d{3,6}\b', re.I)
_SA = re.compile(r'\bSA\s*[:=]?\s*(\d{1,3})\b', re.I)
_HISTORICAL = re.compile(r'去年|前年|此前|曾经|历史|上次|之前|已(?:经)?(?:更换|修复|维修|解除|恢复|处理)|已排除|'
                         r'\b(?:last year|previously|historical|already (?:replaced|repaired|resolved|cleared)|resolved|cleared)\b', re.I)
_CLAUSE = re.compile(r'[，,。；;\n\r.!?！？]+')
UNSUPPORTED_ACTION_ERROR = '尚无部件故障依据，不能直接建议更换或采购；请先给出核查步骤。'
_REPLACEMENT_ACTION = re.compile(r'(?:建议|立即|直接|应当|应该|应|请|必须)\s*(?:更换|替换|采购|订购|购买)')
_NEGATED_ACTION = re.compile(r'(?:不|不要|不能|不可|不应|无需|避免|禁止|不得|暂不|尚不)(?:建议|应当|应该|应)?\s*$')
_CONDITIONAL_ACTION = re.compile(r'如果|仅当|只有|若|确认.{0,40}(?:后|时)|检查.{0,40}(?:损坏|异常).{0,8}(?:后|时)')


def _compact(value):
    return re.sub(r'\s+', '', str(value)).casefold()


def _selected_fault_text(record):
    event = (record.get('fault_context') or {}).get('trackunit_event') or {}
    fields = [record.get('symptom', ''), str(event.get('code') or ''), str(event.get('description') or '')]
    if event.get('spn') is not None and event.get('fmi') is not None:
        fields.append(f"SPN {event['spn']} / FMI {event['fmi']}")
    if event.get('sa') is not None:
        fields.append(f"SA {event['sa']}")
    # Never add all machine faults: another event is not proof for this case.
    return ' '.join(fields)


def _same_fault(quote, selected):
    pairs = set(_PAIR.findall(selected))
    quoted_pairs = set(_PAIR.findall(quote))
    # Multiple fault paragraphs in one excerpt cannot establish which component
    # belongs to this case. J1939 is a network standard, not an OEM fault code.
    oem = lambda text: {s.upper() for s in _OEM.findall(text)} - {'J1939', 'J1708', 'J1587'}
    codes, quoted_codes = oem(selected), oem(quote)
    selected_sa, quoted_sa = set(_SA.findall(selected)), set(_SA.findall(quote))
    if len(selected_sa) > 1 or len(quoted_sa) > 1 or (selected_sa and selected_sa != quoted_sa):
        return False
    if pairs:
        # Ignore compact SPN/FMI/SA tokens when looking for a second OEM code.
        other_codes = {code for code in quoted_codes if not re.fullmatch(r'(?:SPN|FMI|SA)\d+', code)}
        return len(pairs) == len(quoted_pairs) == 1 and pairs == quoted_pairs and not other_codes
    return not quoted_pairs and len(codes) == len(quoted_codes) == 1 and codes == quoted_codes


def _names_part(part, text):
    return any(_compact(value) in _compact(text)
               for value in (part['name'], part['part_number']) if len(value) >= 2)


def _selected_event_resolved(record):
    event = (record.get('fault_context') or {}).get('trackunit_event') or {}
    return (str(event.get('status') or '').upper() in {'RESOLVED', 'CLEARED', 'INACTIVE', 'CLOSED'}
            or bool(event.get('cleared_at')))


def _reject_unsupported_actions(advice):
    # Only reject explicit, unqualified AI replacement instructions. Preserve
    # negative/conditional wording and do not rewrite official manual excerpts.
    prose = [advice.get('summary', '')]
    prose.extend(step.get('instruction', '') for step in advice.get('repair_steps', [])
                 if step.get('basis') == 'ai_inspection_suggestion')
    for text in prose:
        for sentence in re.split(r'[。；;\n\r!?！？]+', text):
            for action in _REPLACEMENT_ACTION.finditer(sentence):
                prefix = sentence[:action.start()]
                if not _NEGATED_ACTION.search(prefix) and not _CONDITIONAL_ACTION.search(prefix):
                    raise ValueError(UNSUPPORTED_ACTION_ERROR)


def _support(part, record, manuals):
    kind = part.get('support', 'catalog_only')
    quote = part.get('support_quote', '').strip()
    if kind == 'catalog_only':
        return False
    selected = _selected_fault_text(record)
    named = _names_part(part, quote)
    if kind == 'manual_mapping':
        source = manuals.get(part.get('support_source_id'))
        if not source or not quote or _compact(quote) not in _compact(source['text']):
            raise ValueError('备件关联引用了不存在的手册原文。')
        # Preserve complete original context when judging a quote; a substring
        # must not turn "do not replace" into a positive recommendation.
        return (source.get('applicability') != 'model_reference_only' and named
                and _same_fault(quote, selected)
                and not re.search(r'(?:不要|不得|禁止|不应|无需|不需).{0,8}(?:更换|替换)|do not replace', source['text'], re.I))
    if kind == 'component_observation':
        raw = record.get('symptom', '')
        if not quote or quote not in raw:
            raise ValueError('备件关联引用了不存在的现场观察。')
        # Page descriptions and model hypotheses are not workshop measurements.
        return (record.get('symptom_source') == 'operator_report'
                and not _HYPOTHETICAL.search(raw) and not _HISTORICAL.search(raw)
                and any(_names_part(part, clause) and _COMPLETED.search(clause) and _DAMAGE.search(clause)
                        for clause in _CLAUSE.split(quote)))
    return False


def qualify(advice, record, manuals):
    """Partition checked catalog rows. Only qualified rows reach preparation mail.

    This is an evidence gate, not a claim of automatic diagnostic correctness.
    The model ranks hypotheses; unsupported catalog relationships stay inspections.
    """
    selected = _selected_fault_text(record)
    communication = bool(_COMM.search(selected))
    resolved = _selected_event_resolved(record)
    separate_power_observation = (record.get('symptom_source') == 'operator_report'
                                  and bool(_POWER_OBSERVATION.search(record.get('symptom', '')))
                                  and not _HYPOTHETICAL.search(record.get('symptom', ''))
                                  and not _HISTORICAL.search(record.get('symptom', '')) and not resolved)
    manual_by_id = {p['source_id']: p for p in manuals}
    candidates, inspections = [], []
    for part in advice['parts']:
        supported = _support(part, record, manual_by_id) and not resolved
        relation = part.get('fault_relation', 'unmapped')
        if relation == 'unmapped':
            continue
        # A supply check can be useful for CAN faults. A supply replacement
        # candidate needs evidence beyond the communication code itself.
        if communication and _POWER_PART.search(part['name']) and not (supported or separate_power_observation):
            continue
        if supported:
            candidates.append({**part, 'evidence_level': 'conditional_candidate', 'status': 'candidate_requires_inspection'})
        else:
            inspections.append({**part, 'evidence_level': 'inspection_only', 'status': 'inspection_only'})
    if not candidates:
        _reject_unsupported_actions(advice)
    return {**advice, 'parts': candidates[:3], 'inspection_targets': inspections[:max(0, 3-len(candidates))]}
