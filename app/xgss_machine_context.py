"""Small, identity-free projection of already-loaded equipment observations.

No disk, network or model calls. Measurement channels retain their own times;
the latest position update must not make an older counter appear current.
"""
from datetime import datetime, timezone

from app.fault_evidence import assess_fault_events
from app.telemetry_evidence import number, ordered_samples, timestamp


def build_context(machine_id, telemetry, faults, now=None):
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Reference time must include timezone')
    ordered,excluded=ordered_samples(machine_id,telemetry,now)
    metrics={}
    for field,unit in (('operating_hours','h'),('idle_hours','h'),('fuel_remaining_percent','%')):
        metric={'value':None,'unit':unit,'observed_at':None,'age_hours':None,'stale_after_24h':None}
        for instant,sample in reversed(ordered):
            value=getattr(sample,field)
            if not number(value) or value<0 or (field=='fuel_remaining_percent' and value>100):
                continue
            age=(now-instant).total_seconds()/3600
            metric.update(value=value,observed_at=instant.isoformat(),age_hours=round(age,4),stale_after_24h=age>24)
            break
        metrics[field]=metric
    events=assess_fault_events(machine_id,faults,now)
    # Project individually: assess_fault_events also carries device identifiers.
    fault_fields=('fault_code','spn','fmi','severity','status')
    recent=[]
    for event in events['events'][-8:]:
        recent.append({**{field:event[field] for field in fault_fields},
                       'occurred_at':timestamp(event['occurred_at']).isoformat()})
    return {
        'as_of':now.astimezone(timezone.utc).isoformat(),
        'last_sample_at':ordered[-1][0].isoformat() if ordered else None,
        'sample_count':len(ordered),'excluded_samples':dict(excluded),'metrics':metrics,
        'faults':recent,
        # Count this machine's loaded records, including ones omitted for bad
        # timestamps; records for unrelated machines do not inflate its count.
        'fault_records_loaded_total':sum(fault.machine_id==machine_id for fault in faults),
        'fault_coverage':'unknown',
        'limitations':[
            '仅使用已载入记录，未实时请求 Trackunit；缺少故障记录不能证明设备无故障。',
            '各指标具有独立采样时间；空值表示没有有效观测，超过 24 小时仅为数据陈旧提示，不是厂家故障阈值。',
            '工时是累计计数，燃油是余量百分比；这些指标不能独立证实冷却系统或其他部件故障。',
            '仅展示最近 8 条同机有效故障记录；状态为记录中的历史状态，故障码不是备件料号。',
        ],
    }
