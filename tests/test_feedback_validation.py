import pytest
from app.feedback_validation import feedback_conflict


EVIDENCE = {'operator:feedback': {'records': [{'feedback_id': 'demo',
    'notes': '模拟检查记录：目视未发现接头松脱；尚未测量压力信号，无法确认传感器是否损坏。'}]}}


@pytest.mark.parametrize('summary', [
    '未检查线束和接头。', '未进行线束和接头的检查。', '尚未进行目视检查。',
    'No physical checks were performed.',
    'Operator feedback indicates no loose connections or sensor damage.',
    '传感器没有损坏。',
])
def test_known_feedback_contradictions_are_detected(summary):
    conflict = feedback_conflict(summary, EVIDENCE)
    assert conflict and conflict['feedback_id'] == 'demo'
    assert conflict['original_notes'] == EVIDENCE['operator:feedback']['records'][0]['notes']


@pytest.mark.parametrize('summary', [
    '人工称目视未发现接头松脱；尚未测量压力信号，无法确认传感器是否损坏。',
    '未完成全面检查。', '未进行电气测量。', '未检查液压泵。',
    '无法确认是否已进行目视检查。',
    'Visual inspection found no loose connector. Pressure measurements are still missing.',
])
def test_remaining_measurements_and_uncertainty_are_not_blanket_denials(summary):
    assert feedback_conflict(summary, EVIDENCE) is None


def test_check_text_is_not_proof_of_performed_inspection():
    evidence = {'operator:feedback': {'records': [{'notes': '尚未进行目视检查。',
        'check_text': '已完成目视检查', 'outcome': 'not_observed'}]}}
    assert feedback_conflict('未检查线束和接头。', evidence) is None
    assert feedback_conflict('未检查线束和接头。', {}) is None
