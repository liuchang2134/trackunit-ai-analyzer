"""Detect narrow, explicit contradictions with operator notes; not a general fact checker."""
import re


def feedback_conflict(summary: str, evidence: dict) -> dict | None:
    records = evidence.get('operator:feedback', {}).get('records', [])
    for record in records:
        notes = record.get('notes', '')
        # Recognize reported visual observations, not the selected multi-action procedure.
        visual = re.search(r'目视(?:检查)?(?:未发现|发现|可见)|已(?:完成|进行)(?:了)?目视检查'
                           r'|\bvisual inspection (?:found|showed|revealed|was performed)\b', notes, re.I)
        uncertain_sensor = re.search(r'无法确认传感器(?:是否)?损坏|\bcannot confirm (?:whether )?(?:the )?sensor (?:is )?damaged\b', notes, re.I)
        for clause in re.split(r'[。！？；;!?\n]|(?<!\d)\.(?!\d)', summary):
            # Verification questions and recommendations are not claims that no check occurred.
            if re.search(r'是否|无法确认|不能确认|\b(?:whether|cannot confirm|verify whether)\b', clause, re.I):
                continue
            denied = re.search(r'(?:尚未|未)(?:进行|做过|做|完成)?(?:任何|实际|现场|目视)?检查(?:线束和接头|接头|线束)?(?=[，,：:\s]|$)'
                               r'|未进行(?:线束和接头|接头|线束)的检查'
                               r'|\bno (?:physical |visual )?(?:checks?|inspection) (?:were|was|has been) performed\b', clause, re.I)
            # A missing specific measurement or comprehensive inspection does not negate a visual check.
            if visual and denied and not re.search(r'测量|全面|详细|电气|pressure|electrical|comprehensive', denied.group(), re.I):
                return {'reason': 'reported_visual_inspection_denied', 'feedback_id': record.get('feedback_id'),
                        'original_notes': notes, 'conflicting_clause': clause}
            cleared_sensor = re.search(r'传感器(?:没有|未|无)损坏|\bno\b[^.;。；]{0,60}\bsensor damage\b'
                                       r'|\bsensor is (?:undamaged|not damaged)\b', clause, re.I)
            if uncertain_sensor and cleared_sensor:
                return {'reason': 'uncertain_sensor_damage_reported_as_absent', 'feedback_id': record.get('feedback_id'),
                        'original_notes': notes, 'conflicting_clause': clause}
    return None
