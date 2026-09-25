"""Bilingual catalog navigation, separate from fault/part recommendation evidence.

Routes select assemblies to inspect; only actual catalog rows supply part numbers.
In particular, engine oil must not be routed to chassis central greasing.
"""
import re


def normalized(value):
    return re.sub(r'[\s_\-/()（）]+', '', str(value)).casefold()


GROUPS = (
    ('变速箱', 'transmission', 'gearbox', '双变'),
    ('变矩器', 'torqueconverter'),
    ('变速箱油散热器', '双变油散芯体', 'transmissionoilcooler'),
    ('线束', '线缆', 'harness'),
    ('插接件', '接插件', '连接器', 'connector'),
    ('后处理', 'aftertreatment', 'scr'),
    ('尿素箱', '尿素罐', 'deftank', 'ureatank'),
    ('尿素泵', 'defpump', 'ureapump'),
    ('尿素喷嘴', '尿素喷射', 'ureainjector', 'definjector'),
    ('机油泵', '润滑油泵', 'engineoilpump', 'lubricatingoilpump'),
    ('机油滤清器', '机油滤芯', '润滑油滤清器', 'engineoilfilter'),
    ('机油压力', '润滑油压力', 'oilpressure'),
    ('油底壳', 'oilsump', 'oilpan'),
    ('冷却系统', 'cooling'),
    ('冷却液泵', '水泵', 'waterpump', 'coolantpump'),
    ('节温器', 'thermostat'),
    ('中冷器', '中冷芯体', 'intercooler', 'aftercooler'),
    ('散热器', 'radiator'),
    ('冷却风扇', '风扇', 'coolingfan'),
    ('蓄电池', 'battery'),
)


def term_matches(name, term):
    name, term = normalized(name), normalized(term)
    if '集中润滑' in name and any(s in term for s in ('机油', '润滑油', '油压', '润滑系统', 'engineoil', 'oilpressure')):
        return False
    if term in name or name in term:
        return True
    for aliases in GROUPS:
        for alias in aliases:
            if alias not in term:
                continue
            # Keep the component qualifier: "transmission oil filter" must not
            # become every transmission housing merely by sharing its system.
            if any(term.replace(alias, replacement) in name for replacement in aliases):
                return True
    specific = {
        'transmissionharness': ('工作机线缆', '变速箱线束'),
        'transmissionecu': ('变速箱控制', '控制单元'),
        '变速箱控制器': ('控制单元',),
        'can': ('电气系统', '线缆', '线束'),
        '总线': ('电气系统', '线缆', '线束'),
        '冷却液': ('冷却系统',),
    }
    return any(alias in name for alias in specific.get(term, ()))


def route_score(name, terms):
    """1 = ancestor to expand; 2 = relevant assembly whose BOM may contain terms.

    A route is not a matched search term, nor evidence of a damaged part.
    """
    name = normalized(name)
    queries = [normalized(term) for term in terms]
    wanted = '|'.join(queries)
    oil = any(
        any(t in query for t in ('机油', '润滑油', '油底壳', '润滑系统', 'engineoil', 'oilsump', 'oilpan'))
        or (any(t in query for t in ('油压', 'oilpressure'))
            and not any(t in query for t in ('变速箱', '变矩器', '传动', '液压', '制动', 'transmission', 'gearbox', 'hydraulic', 'brake', 'torqueconverter')))
        for query in queries)
    exhaust = any(t in wanted for t in ('尿素', '后处理', 'deftank', 'defpump', 'definjector', 'urea', 'aftertreatment', 'scr'))
    cooling = any(t in wanted for t in ('冷却', '散热器', '中冷', '节温器', '水泵', 'cooling', 'radiator', 'thermostat', 'coolant', 'intercooler', 'aftercooler'))
    if (oil or exhaust or cooling) and name in ('发动机', '发动机系统', '发动机总成', 'engine', 'enginesystem'):
        return 1
    if exhaust and '后处理' in name:
        return 2
    if oil and '集中润滑' not in name and any(t in name for t in ('润滑油', '机油', '油底壳', '油位测量')):
        return 2
    if cooling and ('冷却系统' in name or '进排气组件' in name):
        return 1
    transmission = any(t in wanted for t in ('变速箱', '变矩器', '传动油', 'transmission', 'gearbox', 'torqueconverter'))
    if transmission:
        if name in ('双变系统', '传动系统') or '双变油散' in name:
            return 2
        if name in ('变速箱', '变速箱总成', '变速箱总成国产', 'transmission', 'gearbox'):
            return 1
        if any(t in wanted for t in ('散热', '油温', 'oilcooler', 'oiltemperature')) and name in ('冷却系统', '散热器安装组件', '散热器总成'):
            return 2 if name=='散热器总成' else 1
    if any(t in wanted for t in ('液压', 'hydraulic')) and name in ('液压系统', '工作液压系统', 'hydraulicsystem'):
        return 2
    if any(t in wanted for t in ('线束', '线缆', '插接件', '接插件', 'harness', 'connector', '总线')) and '电气' in name:
        return 1
    return 0
