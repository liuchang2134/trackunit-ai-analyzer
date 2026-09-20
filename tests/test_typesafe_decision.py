"""The ranking layer must degrade to retrieval order, never to a broken analysis.

This layer sits between manual retrieval and the model that reads the sections. If it
raised, or returned a partial order, the whole investigation would fail for something
that is only an optimisation. So the tests spend most of their effort on the failure
paths, and every one of them asserts the caller still gets usable records.

No test here touches the network: the SDK is only asked to construct a client and to
build question objects, both of which are local operations.
"""
import json

import pytest

from app import typesafe_decision as td


def record(reference_id, *, section='Possible cause', text='Fuse blow. Check the ECU fuse.'):
    return {'reference_id': reference_id, 'section': section, 'text': text}


class Answer:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeClient:
    """Answers every question, with values the test controls per reference id."""

    def __init__(self, answers=None, raises=None):
        self.answers = answers or {}
        self.raises = raises
        self.calls = []

    def system_one(self, *, state, questions, timeout=None, **kwargs):
        self.calls.append({'state': state, 'questions': list(questions), 'timeout': timeout})
        if self.raises:
            raise self.raises
        answers = {}
        for record in state['excerpts']:
            key = record['reference_id']
            spec = self.answers.get(key, {'relevance': 0.5, 'states_cause': False, 'strength': 1.0})
            answers[f'{key}__relevance'] = Answer(noul=spec['relevance'], confidence=spec.get('confidence', 0.9))
            answers[f'{key}__states_cause'] = Answer(
                choice='states_cause' if spec['states_cause'] else 'context_only')
            answers[f'{key}__strength'] = Answer(score=spec['strength'])
        return Answer(answers=answers)


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)


def test_no_candidates_returns_an_empty_ranking():
    ranking = td.rank_manual_records('E4030', [], client=FakeClient())
    assert ranking.ranked is False and ranking.reason == 'no_candidates'


def test_without_a_key_the_layer_is_skipped_and_reported(monkeypatch):
    # The caller must be able to tell "not configured" from "ranked and found nothing".
    assert td.jev_configured() is False
    ranking = td.rank_manual_records('E4030', [record('manual:a')])
    assert ranking.ranked is False
    assert ranking.reason == 'not_configured'
    assert td.describe(ranking)['ranked'] is False


def test_a_configured_key_is_detected(monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', '  test-key  ')
    assert td.jev_configured() is True


def test_records_are_ordered_by_relevance_then_cause_then_strength():
    records = [record('manual:weak'), record('manual:strong'), record('manual:passing')]
    client = FakeClient({
        'manual:weak': {'relevance': 0.6, 'states_cause': False, 'strength': 2.0},
        'manual:strong': {'relevance': 0.9, 'states_cause': True, 'strength': 3.0},
        'manual:passing': {'relevance': 0.2, 'states_cause': True, 'strength': 3.0},
    })
    ranking = td.rank_manual_records('E4030', records, client=client)
    assert ranking.ranked is True
    assert [score.reference_id for score in sorted(ranking.scores, key=lambda s: s.order)] == [
        'manual:strong', 'manual:weak', 'manual:passing']
    assert ranking.scores[0].order == 1 or ranking.scores[1].order == 1
    assert ranking.method == 'jev_system_one'


def test_a_stated_cause_breaks_a_relevance_tie():
    records = [record('manual:context'), record('manual:cause')]
    client = FakeClient({
        'manual:context': {'relevance': 0.8, 'states_cause': False, 'strength': 1.0},
        'manual:cause': {'relevance': 0.8, 'states_cause': True, 'strength': 1.0},
    })
    ranking = td.rank_manual_records('E4030', records, client=client)
    ordered = [s.reference_id for s in sorted(ranking.scores, key=lambda s: s.order)]
    assert ordered == ['manual:cause', 'manual:context']


def test_the_relevance_floor_is_applied_and_reported():
    records = [record('manual:above'), record('manual:below')]
    client = FakeClient({
        'manual:above': {'relevance': 0.9, 'states_cause': True, 'strength': 3.0},
        'manual:below': {'relevance': 0.1, 'states_cause': False, 'strength': 1.0},
    })
    described = td.describe(td.rank_manual_records('E4030', records, client=client))
    flags = {item['reference_id']: item['above_floor'] for item in described['sections']}
    assert flags == {'manual:above': True, 'manual:below': False}
    # Below-floor sections are still returned; the floor only labels them.
    assert {s.reference_id for s in td.rank_manual_records('E4030', records, client=client).scores} == {
        'manual:above', 'manual:below'}


def test_a_provider_error_degrades_to_retrieval_order():
    records = [record('manual:a'), record('manual:b')]
    client = FakeClient(raises=RuntimeError('provider exploded'))
    ranking = td.rank_manual_records('E4030', records, client=client)
    assert ranking.ranked is False
    assert ranking.method == 'unavailable' and ranking.reason == 'RuntimeError'
    assert td.reorder_records(ranking, records) == records, 'records must survive a provider failure'


@pytest.mark.parametrize('error', [
    RuntimeError('unexpected provider bug'),
    KeyError('malformed response'),
    TypeError('sdk signature changed'),
    TimeoutError('provider too slow'),
    MemoryError('absurd payload'),
])
def test_any_error_degrades_instead_of_failing_the_investigation(error):
    # Narrow catching was the original defect: an unanticipated provider error escaped and
    # took the whole analysis with it. This layer is an optimisation, so every error ends
    # as "no ranking" with the reason recorded.
    records = [record('manual:a')]
    ranking = td.rank_manual_records('E4030', records, client=FakeClient(raises=error))
    assert ranking.ranked is False
    assert ranking.reason == type(error).__name__
    assert td.reorder_records(ranking, records) == records


def test_a_timeout_is_passed_so_a_slow_provider_cannot_stall_the_analysis():
    client = FakeClient()
    td.rank_manual_records('E4030', [record('manual:a')], client=client)
    assert client.calls[0]['timeout'] == td.DEFAULT_TIMEOUT_SECONDS


def test_incomplete_answers_are_rejected_rather_than_partially_applied():
    # Half a ranking would silently reorder some sections and not others.
    class PartialClient:
        def system_one(self, *, state, questions, timeout=None):
            key = state['excerpts'][0]['reference_id']
            return Answer(answers={f'{key}__relevance': Answer(noul=0.9, confidence=0.9)})

    ranking = td.rank_manual_records('E4030', [record('manual:a'), record('manual:b')],
                                     client=PartialClient())
    assert ranking.ranked is False and ranking.reason == 'incomplete_answers'


def test_an_unexpected_response_shape_is_reported_not_crashed():
    class ShapeClient:
        def system_one(self, *, state, questions, timeout=None):
            return Answer(answers=None)

    ranking = td.rank_manual_records('E4030', [record('manual:a')], client=ShapeClient())
    assert ranking.ranked is False and ranking.reason == 'unexpected_response'


def test_one_question_set_is_sent_per_candidate():
    records = [record('manual:a'), record('manual:b')]
    client = FakeClient()
    td.rank_manual_records('E4030', records, client=client)
    asked = client.calls[0]['questions']
    assert len(asked) == 6, 'three questions per candidate'
    assert 'manual:a__relevance' in asked and 'manual:b__strength' in asked


def test_excerpt_text_is_truncated_before_it_is_sent():
    long_text = 'x' * 9000
    client = FakeClient()
    td.rank_manual_records('E4030', [record('manual:a', text=long_text)], client=client)
    sent = client.calls[0]['state']['excerpts'][0]['text']
    assert len(sent) < len(long_text), 'a huge section must not be sent whole'


def test_reordering_keeps_unscored_records_at_the_end():
    records = [record('manual:a'), record('manual:b')]
    ranking = td.Ranking(ranked=True, method='test', scores=[
        td.SectionScore('manual:b', 0.9, 0.9, True, 3.0, 1),
    ])
    assert [r['reference_id'] for r in td.reorder_records(ranking, records)] == ['manual:b', 'manual:a']


def test_reordering_is_a_no_op_when_nothing_was_ranked():
    records = [record('manual:a'), record('manual:b')]
    ranking = td.Ranking(ranked=False, method='none', reason='not_configured')
    assert td.reorder_records(ranking, records) == records


def test_the_description_is_json_serialisable_for_the_report():
    records = [record('manual:a')]
    described = td.describe(td.rank_manual_records('E4030', records, client=FakeClient()))
    json.dumps(described)
    assert described['relevance_floor'] == td.RELEVANCE_FLOOR
    assert described['sections'][0]['reference_id'] == 'manual:a'


def test_the_sdk_can_construct_a_client_and_questions_without_a_network_call():
    # Proves the integration is wired to the real SDK surface, not just to the fake.
    import typesafe_sdk

    client = typesafe_sdk.TypeSafeClient(api_key='probe-only')
    questions = td._build_questions('E4030', [record('manual:a')])
    assert set(questions) == {'manual:a__relevance', 'manual:a__states_cause', 'manual:a__strength'}
    assert all(hasattr(item, 'model_dump') for item in questions.values())
