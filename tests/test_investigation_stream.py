"""The streamed investigation must report real progress and really stop.

These tests never contact a provider: the structured-decision call is replaced,
so they prove the stream, the cancel and the event vocabulary, not model quality.
"""
import json
import threading
import time

import pytest

from app import local_assistant as agent
from app.investigation_stream import stream_investigation
from app.local_assistant import InvestigationRequest


@pytest.fixture
def deepseek(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'deepseek')
    monkeypatch.setenv('DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'private-deepseek-test-key')
    monkeypatch.setattr(agent.httpx, 'post', lambda *a, **k: pytest.fail('No live provider request'))
    return monkeypatch


def finish_decision(summary='已核对证据后给出结论。'):
    return json.dumps({'action': 'finish', 'component': '', 'summary': summary,
                       'evidence_ids': [], 'next_check_ids': []})


def payload(**overrides):
    """A minimal valid investigation request for the stream lifecycle tests."""
    base = {'machine_id': 'M-1001', 'question': '检查当前设备的异常', 'task': 'overview', 'language': 'zh'}
    base.update(overrides)
    return base


def request(**overrides):
    return InvestigationRequest.model_validate(payload(**overrides))


def collect(stream, timeout=15.0):
    """Drain SSE frames into decoded events, ignoring heartbeats."""
    events, deadline = [], time.monotonic() + timeout
    for frame in stream:
        if frame.startswith(':'):
            if time.monotonic() > deadline:
                break
            continue
        events.append(json.loads(frame[len('data: '):]))
        if events[-1]['type'] == 'end':
            break
    return events


def test_progress_events_describe_completed_work_and_precede_the_result(deepseek):
    calls = []

    def decide(messages, schema, **kwargs):
        calls.append(len(calls) + 1)
        return finish_decision()

    deepseek.setattr(agent, 'generate_structured_with_deepseek', decide)
    events = collect(stream_investigation(request()))

    stages = [event['stage'] for event in events if event['type'] == 'progress']
    # Progress must name work that actually happened, in the order it happened:
    # context preparation, then the real reads, then numbered model decisions.
    assert stages[0] == 'prepare'
    assert 'reading' in stages
    assert 'model_decision' in stages
    assert stages.count('model_decision') == len(calls)
    decisions = [event for event in events if event.get('stage') == 'model_decision']
    assert [event['step'] for event in decisions] == list(range(1, len(calls) + 1))
    messages = ' '.join(event['message'] for event in events if event['type'] == 'progress')
    assert '快照' in messages, 'a real read must be reported'
    # A finish decision without the required evidence cannot produce a report, so
    # this run legitimately ends in an error. Either way the stream is terminated
    # by exactly one end frame and never renders partial model output.
    assert events[-1]['type'] == 'end'
    assert [event['type'] for event in events].count('end') == 1
    assert not any(event['type'] == 'result' for event in events)
    assert events[-2]['type'] == 'error'
    assert events[-2]['kind'] == 'analysis_incomplete'
    if 'finalizing' in stages:
        assert stages.index('finalizing') > stages.index('model_decision')


def test_a_completed_investigation_emits_the_validated_report_then_ends(deepseek):
    # The success path only ever publishes the report returned by investigate();
    # no partial model output reaches the stream.
    report = {'status': 'completed', 'machine_id': 'M-1001', 'summary': '已核对证据。',
              'component_hypotheses': [], 'parts_candidates': []}
    deepseek.setattr(agent, 'investigate', lambda incoming: dict(report))
    events = collect(stream_investigation(request()))
    tail = [event for event in events if event['type'] != 'progress']
    assert [event['type'] for event in tail] == ['result', 'end']
    assert tail[0]['report'] == report


def test_a_disconnected_reader_cancels_the_investigation(deepseek):
    calls, release = [], threading.Event()

    def decide(messages, schema, **kwargs):
        calls.append(len(calls) + 1)
        release.wait(5)
        return finish_decision()

    deepseek.setattr(agent, 'generate_structured_with_deepseek', decide)
    stream = stream_investigation(request())
    next(stream)                      # first progress frame
    deadline = time.monotonic() + 5
    while not calls and time.monotonic() < deadline:
        time.sleep(0.02)
    assert calls, 'the first model decision should have started'
    stream.close()                    # the reader went away
    release.set()
    time.sleep(0.3)
    # The worker must not begin another model call for a report nobody reads.
    assert len(calls) == 1


def test_cancel_before_the_next_model_call_really_stops_the_investigation(deepseek):
    calls, release = [], threading.Event()
    original = agent.investigation_progress

    def decide(messages, schema, **kwargs):
        calls.append(len(calls) + 1)
        release.wait(5)
        return finish_decision()

    deepseek.setattr(agent, 'generate_structured_with_deepseek', decide)
    stream = stream_investigation(request())
    # Drain until the first model decision is announced, then stop reading and
    # cancel, so the assertion covers "no further call" rather than "no call".
    for frame in stream:
        if 'model_decision' in frame:
            break
    deadline = time.monotonic() + 5
    while not calls and time.monotonic() < deadline:
        time.sleep(0.02)
    assert calls, 'the first decision should have started'
    stream.close()
    release.set()
    time.sleep(0.3)
    assert len(calls) == 1, 'a cancelled investigation must not start another model call'
    assert original is agent.investigation_progress


def test_a_provider_failure_is_reported_as_an_error_event_not_a_partial_report(deepseek):
    from app.deepseek_client import DeepSeekError

    def fail(*args, **kwargs):
        raise DeepSeekError('DeepSeek API rate limit was exceeded. Please retry later.', kind='rate_limit')

    deepseek.setattr(agent, 'generate_structured_with_deepseek', fail)
    events = collect(stream_investigation(request()))
    tail = [event for event in events if event['type'] != 'progress']
    assert [event['type'] for event in tail] == ['error', 'end']
    assert tail[0]['kind'] == 'rate_limit'
    assert 'rate limit' in tail[0]['message']
    assert not any(event['type'] == 'result' for event in events)


def test_the_api_streams_one_investigation_in_a_single_request(deepseek):
    # The run must not depend on server-side state surviving between requests:
    # a second request may be handled by a different worker process, which is
    # exactly how a "device never associates" failure appears to the user.
    from fastapi.testclient import TestClient
    from app.main import app

    deepseek.setattr(agent, 'investigate', lambda incoming: {'status': 'completed', 'machine_id': 'M-1001',
                                                             'summary': '已核对证据。', 'parts_candidates': [],
                                                             'component_hypotheses': []})
    client = TestClient(app)
    with client.stream('POST', '/assistant/investigate/stream', json=payload()) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        assert response.headers['cache-control'] == 'no-store'
        events = []
        for line in response.iter_lines():
            if not line.startswith('data: '):
                continue
            events.append(json.loads(line[len('data: '):]))
            if events[-1]['type'] == 'end':
                break
    assert events[-1]['type'] == 'end'
    assert events[-2]['type'] == 'result'
    assert events[-2]['report']['status'] == 'completed'
    # This stub replaces investigate() wholesale, so only the terminal frames are
    # produced here; the progress vocabulary is covered by the tests above.
    assert not any(event['type'] == 'error' for event in events)


def test_the_api_rejects_an_invalid_request_before_starting_any_work(deepseek):
    from fastapi.testclient import TestClient
    from app.main import app

    deepseek.setattr(agent, 'investigate', lambda incoming: pytest.fail('no investigation may start'))
    client = TestClient(app)
    assert client.post('/assistant/investigate/stream', json={'machine_id': 'M-1001'}).status_code == 422
