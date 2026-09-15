import pytest
from app.summary_time_validation import unsupported_time_equality


def evidence(sample='2026-06-29T08:45:00Z'):
    return {'tool:1:snapshot': {'replay_at': '2026-06-29T08:55:00Z', 'telemetry': [{'recorded_at': sample}]}}


@pytest.mark.parametrize('summary', [
    '模拟数据回放时间与记录时间一致，仅适用于该片段。',
    'The replay time matches the recorded timestamp.',
    'The sample timestamp and replay time are identical.',
])
def test_wrong_equality_rejected_with_actual_timestamps(summary):
    result = unsupported_time_equality(summary, evidence())
    assert result['replay_cutoff'].endswith('08:55:00+00:00')
    assert result['displayed_sample_timestamps'] == ['2026-06-29T08:45:00+00:00']


@pytest.mark.parametrize('summary', [
    '回放时间与采样时间不一致。', '请核对回放时间与记录时间是否一致。',
    'The replay time does not match the sample timestamp.', 'Verify whether replay and sample timestamps match.',
])
def test_negations_and_checks_are_not_assertions(summary):
    assert unsupported_time_equality(summary, evidence()) is None


def test_equal_instants_in_different_timezones_are_supported():
    assert unsupported_time_equality('回放时间与采样时间相同。', evidence('2026-06-29T04:55:00-04:00')) is None


def test_latest_qualifier_does_not_imply_all_records_equal_cutoff():
    data = evidence()
    data['tool:1:snapshot']['telemetry'].append({'recorded_at': '2026-06-29T08:55:00Z'})
    assert unsupported_time_equality('最新采样时间与回放时间一致。', data) is None
    assert unsupported_time_equality('采样时间与回放时间一致。', data) is not None


def test_missing_evidence_does_not_support_equality():
    assert unsupported_time_equality('回放时间与记录时间一致。', {}) is not None
    assert unsupported_time_equality('回放时间与记录时间一致。', evidence('invalid')) is not None
