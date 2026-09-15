"""Check explicit replay/sample equality claims against loaded timestamps."""
import re
from app.telemetry_evidence import timestamp


def unsupported_time_equality(summary: str, evidence: dict) -> dict | None:
    """Return conflicting facts for a recognized affirmative claim, not general NLP validation."""
    for clause in re.split(r'[。！？；;!?\n]', summary):
        if not re.search(r'回放|分析截止|replay|analysis cutoff', clause, re.I):
            continue
        if not re.search(r'采样|记录时间|记录时刻|sample|record(?:ed)?\s+(?:time|timestamp)', clause, re.I):
            continue
        if not re.search(r'一致|相同|相等|相符|\b(?:match(?:es)?|equal(?:s)?|identical|same)\b', clause, re.I):
            continue
        if re.search(r'不一致|不相同|不相等|不相符|是否|不能|无法|未确认|尚未|核对|核实|确认是否|\b(?:not|whether|cannot|verify|check|unconfirmed)\b', clause, re.I):
            continue
        snapshot = next(((ref, item) for ref, item in evidence.items() if ref.endswith(':snapshot')), None)
        if snapshot is None:
            return {'reason': 'no_snapshot_evidence'}
        ref, item = snapshot
        cutoff = timestamp(item.get('replay_at'))
        instants = {value for row in item.get('telemetry', []) if (value := timestamp(row.get('recorded_at'))) is not None}
        latest_claim = bool(re.search(r'最新|最近|latest|most recent', clause, re.I))
        compared = {max(instants)} if latest_claim and instants else instants
        if cutoff is None or not compared or compared != {cutoff}:
            return {'reason': 'equality_not_supported', 'evidence_id': ref,
                    'replay_cutoff': cutoff.isoformat() if cutoff else None,
                    'displayed_sample_timestamps': sorted(value.isoformat() for value in instants),
                    'scope': 'latest_sample' if latest_claim else 'displayed_samples'}
    return None
