"""Hour-based AI maintenance context, without inventing service intervals."""
import copy
import math
import re

PLAN_INSTRUCTIONS = (
    '当前任务是预防性保养与易损件推荐，不是故障诊断。没有可用故障数据也应开展此任务，但不能称设备健康。'
    '结合机型、累计工时及采样时间，选择最多三个适用的保养/易损部件检索方向，由你判断优先级并解释原因。'
    '优先查找滤清器/滤芯、润滑与保养分类、机型适用的磨损件；这些是检索方向，不是已经读到的零件。'
    '每个方向最多四个检索词，按一级系统、中间分类、目标部件、必要同义词排列，不能全部给叶子部件同义词。'
    '检索词优先包含图册常用短词：如发动机、空滤、机滤、润滑。空气滤清器也可能写成空滤器，不能只提供一种长名称。'
    '仅按提供的 model 和 machine_type 判断机型；机型未知时先查保养、润滑、滤清器等通用分类，不能猜成装载机、挖掘机或起重机。'
    'machine_type 已明确时不得说机型未知或未提供；严格按其机械结构选部件：轮式装载机没有履带、支重轮或托链轮，不能将它们列为待查磨损件。'
    '未确认设备类型时，不加入铲斗、履带、吊臂等机型专属部件。已有类型时也不能跨机种套用。'
    '检索词须使用 XGSS 可能显示的系统与部件名称。不要沿用不存在的故障或默认只查冷却系统。'
    '当前尚未获得厂家保养周期或上次保养记录，不能按整百工时推定到期，不给具体更换小时数。'
    '工时为空时仍可按机型查找候选，但注明需补工时；历史工时不能当作实时值。'
    '计划摘要说明 AI 如何根据现有工时及机型选择资料方向，不能把通用常识说成厂家手册要求。'
)

# Exact models whose machine type is identified by the linked XCMG product page.
# Keep this bounded: an XC prefix alone is not evidence of a specific machine.
OFFICIAL_MODEL_TYPES = {
    'XC948U': '轮式装载机',
    'XE55U': '履带式挖掘机',
    'XE80U': '履带式挖掘机',
    'XE135U': '履带式挖掘机',
}


def resolved_machine_type(model, machine_type=None):
    declared = str(machine_type or '').strip()
    if declared:
        return declared
    return OFFICIAL_MODEL_TYPES.get(str(model or '').strip().upper(), '')

ADVICE_INSTRUCTIONS = (
    '当前任务是 AI 工时保养与易损件推荐。根据同机工时快照和本次实际 XGSS 条目，筛选维护候选并按检查优先级排序。'
    'parts 中 part_role 用 maintenance 表示保养件、wear 表示易损件；只选实际提供的 source_id，不把整图螺栓和支架充作推荐。'
    'reason 要说明该件的保养/磨损作用以及当前累计工时对检查优先级的意义；工时不足以证明损坏或达到更换期限。'
    'replacement_condition 说明应先核对何种保养记录、原厂周期或现场磨损/堵塞情况，满足什么条件才考虑准备或更换。'
    '缺少保养历史与周期时仅建议检查和核对记录，不能自定250/500/1000等周期，不预测到期时间，也不默认从零工时未保养。'
    '找不到相关保养件或易损件则 parts 为空，并提出下一步要查的分类，不能强行把已有不相关零件当成候选。'
    'repair_steps 在本任务中表示保养检查建议；summary 简短说明AI筛选依据与当前工时，图片、料号均由真实资料绑定。'
    '严格按提供的机型或实际图册类别，不从未知机型推断专属部件；整机目录行不是保养备件，不推荐更换整台机器。'
    '只围绕已取得的候选给检查建议，未取得的分类列入missing_evidence，不凑步骤；没有可用候选时允许parts和repair_steps均为空。'
    'summary 限两句，推荐理由和更换条件各尽量控制在100汉字内；采样时间与周期缺口只在必要处简述，不反复复述。'
)


def project_machine_context(machine_context):
    if machine_context is None:
        return None
    allowed = ('as_of', 'last_sample_at', 'sample_count', 'excluded_samples', 'metrics', 'source')
    return {key: copy.deepcopy(machine_context[key]) for key in allowed if key in machine_context}


def build_context(machine_context):
    raw = copy.deepcopy(((machine_context or {}).get('metrics') or {}).get('operating_hours') or {})
    value = raw.get('value')
    valid = type(value) in (float, int) and math.isfinite(value) and value >= 0
    metric = {key: raw.get(key) for key in ('value', 'unit', 'observed_at', 'age_hours', 'stale_after_24h')}
    if not valid:
        metric['value'] = None
    metric['unit'] = 'h'
    return {'operating_hours': metric, 'interval_status': 'unverified',
            'service_history_status': 'unknown', 'last_service_hours': None,
            'recommendation_basis': 'hours_and_model_inspection' if valid else 'model_only_inspection'}


def default_question():
    return '请结合当前机型与已载入工时，在同机 XGSS 资料中筛选保养件和易损件，说明检查优先级、推荐理由及考虑更换的条件。'


_HOURS = r'\d+(?:\.\d+)?\s*(?:个)?\s*(?:小时|工时|h(?![a-z]))'
_SCHEDULE_CLAIMS = (
    re.compile(r'(?:每(?:隔)?|间隔|周期[为是：:\s]*|还[剩需]|剩余|再运行)\s*' + _HOURS, re.I),
    re.compile(_HOURS + r'\s*(?:时|后|内|之前|以内)?\s*'
               r'(?:(?:应当|应该|应|需要|需|须|必须|建议|进行|安排|就|立即|及时)\s*)*'
               r'(?:保养|更换|换油|维护|检修)', re.I),
    re.compile(r'(?:已经|现已|已|即将|确定|确认|认定)[^。！？!?；;，,\n]{0,8}'
               r'(?:到期|超期|逾期|达到(?:保养|更换)(?:期限|周期))'),
)
_CLAUSE_BREAK = re.compile(r'[。！？!?；;，,\n]|(?:但是|不过|然而|依然|仍然|仍要|仍需|仍建议|因此|所以|但)')
_NEGATED_PREFIX = re.compile(r'(?:不能|无法|不可|不应|不宜|不要|不得|不足以|未能|尚未确认|尚未核实)'
                             r'[^。！？!?；;，,\n]{0,32}$')
_UNKNOWN_SUFFIX = re.compile(r'^\s*(?:的)?(?:说法|周期|要求|计划|依据|记录|历史)?'
                            r'(?:尚未核实|尚未确认|未经核实|未经确认|未核实|未确认|未验证|不适用|并不适用|未知)')


def validate_prose(texts):
    """Reject common unsupported schedules, while retaining explicit uncertainty.

    Negation is scoped to a clause: an earlier disclaimer cannot authorize a
    later affirmative schedule. This is a bounded language check, not a proof
    of every possible claim; the UI still shows unverified service history.
    """
    for text in texts:
        for clause in _CLAUSE_BREAK.split(text):
            for pattern in _SCHEDULE_CLAIMS:
                for match in pattern.finditer(clause):
                    prefix, suffix = clause[:match.start()], clause[match.end():]
                    if (_NEGATED_PREFIX.search(prefix) or '是否' in prefix[-12:]
                            or _UNKNOWN_SUFFIX.search(suffix)):
                        continue
                    raise ValueError('缺少适用保养周期或历史依据，不能生成量化更换周期或到期结论。')


_UNKNOWN_MODELS = {'', 'data not available', 'unknown', '未提供', '未知', '型号未知', '机型未提供'}
_SPECIFIC_COMPONENTS = {
    'bucket': r'铲斗|斗齿|刃板|bucket|cutting\s+edge',
    'track': r'履带|支重轮|托链轮|track\s+shoe|track\s+roller',
    'boom': r'吊臂|吊钩|起升卷扬|hoist|crane\s+boom',
}


def machine_scope(model='', machine_type='', parts=()):
    """Use supplied identity and checked catalog names, never model guesses."""
    labels = [str(model or ''), str(machine_type or '')]
    for part in parts:
        labels.extend([part.get('name', ''), *part.get('assembly_path', [])])
    text = ' '.join(labels)
    crane = bool(re.search(r'起重机|crane', text, re.I))
    loader = bool(re.search(r'装载机|loader|\bXC\d', text, re.I))
    excavator = bool(re.search(r'挖掘机|excavator|\bXE\d', text, re.I))
    return {'identity_known': str(model or '').strip().lower() not in _UNKNOWN_MODELS
            or str(machine_type or '').strip().lower() not in _UNKNOWN_MODELS,
            'crane': crane, 'loader': loader, 'excavator': excavator,
            'catalog_labels': text}


def validate_machine_scope(prose, model='', machine_type='', parts=()):
    scope = machine_scope(model, machine_type, parts)
    text = ' '.join(prose)
    for kind, pattern in _SPECIFIC_COMPONENTS.items():
        if not re.search(pattern, text, re.I):
            continue
        # A checked part name/path supports that direction without guessing a
        # model code. Opposing known machine categories must not be inherited.
        supported = bool(re.search(pattern, scope['catalog_labels'], re.I))
        if kind == 'bucket': supported |= scope['loader'] or scope['excavator']
        if kind == 'boom': supported |= scope['crane']
        if kind == 'track': supported |= scope['excavator'] or bool(re.search(r'履带|crawler|tracked', scope['catalog_labels'], re.I))
        if not supported and (not scope['identity_known'] or scope['crane'] or scope['loader']):
            raise ValueError('机型资料不支持该专属部件，请按已确认设备类型检索。')


def is_machine_catalog_row(part):
    """Only reject an explicit whole-machine row, not its named components."""
    name = part.get('name', '').strip()
    return bool(re.fullmatch(r'(?:[\u4e00-\u9fffA-Za-z -]*(?:起重机|装载机|挖掘机|压路机)|整机)(?:总成)?', name)
                or re.fullmatch(r'(?:[A-Za-z -]*\s)?(?:crane|loader|excavator)', name, re.I))


def validate_plan(plan, *, model='', machine_type=''):
    """The initial search plan is visible evidence for the second model pass."""
    prose = [plan['summary'], *plan.get('missing_evidence', [])]
    for direction in plan['directions']:
        prose.extend((direction['component'], direction['reason'], *direction['search_terms']))
    if resolved_machine_type(model, machine_type) and any(re.search(r'机型(?:未知|未提供|不明)|设备类型(?:未知|未提供|不明)', text) for text in prose):
        raise ValueError('当前机型类别已确认，不能称机型未知或未提供。')
    validate_prose(prose)
    validate_machine_scope(prose, model, machine_type)
    return plan


def validate_advice(advice, *, model='', machine_type='', parts=()):
    """Validate maintenance roles and prose; exact manual text is checked elsewhere."""
    prose = [advice['summary'], *advice.get('missing_evidence', [])]
    for part in advice['parts']:
        if part.get('part_role') not in ('maintenance', 'wear'):
            raise ValueError('保养推荐必须区分保养件与易损件。')
        if is_machine_catalog_row(part):
            raise ValueError('当前读取的是整机目录，不能作为保养备件；请继续读取下级分类。')
        prose.extend((part['reason'], part['replacement_condition']))
    prose.extend(step['instruction'] for step in advice['repair_steps'] if step['basis'] != 'manual_excerpt')
    validate_prose(prose)
    validate_machine_scope(prose, model, machine_type, parts)
    return advice
