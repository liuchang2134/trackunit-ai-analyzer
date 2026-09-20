"""Rank retrieved manual sections with a System One model before the LLM reads them.

Manual retrieval returns every section that carries the fault code (up to twelve). All
of them currently go into the model's context, including sections that only mention the
code in passing. Ranking them first is a bounded judgement:

* is this section relevant to the reported code at all (`Noul`)?
* does this section state a possible cause (`Choice`)?
* how strongly does it bear on the code (`Score`)?

That is exactly the shape Jev is built for — a fixed answer space per question plus a
probability the caller can threshold — and it is deliberately *not* a place to ask a
generative model for an opinion. The final ordering rule, and whether any candidate is
dropped, stays in this module so the behaviour is inspectable and testable offline.

The layer is optional by design. With no key configured, or on any provider error, the
caller keeps the retrieval order, and `ranked` is False so a report never implies the
model ordered something it did not.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_MODEL = 'jev-latest'
DEFAULT_TIMEOUT_SECONDS = 20.0

# A section below this relevance is treated as a passing mention. Kept at module level so
# the threshold is visible and can be argued about rather than buried in a call.
RELEVANCE_FLOOR = 0.5
# Sections that state no possible cause are still kept: a reader may need the page for a
# nearby check even when the wording is not a cause list.
MIN_CAUSES_TO_PREFER = 1


@dataclass(frozen=True)
class SectionScore:
    reference_id: str
    relevance: float
    confidence: float | None
    states_cause: bool
    strength: float | None
    order: int

    @property
    def passes_floor(self) -> bool:
        return self.relevance >= RELEVANCE_FLOOR


@dataclass
class Ranking:
    ranked: bool
    method: str
    scores: list[SectionScore] = field(default_factory=list)
    reason: str | None = None

    def order_of(self, reference_id: str) -> int:
        for score in self.scores:
            if score.reference_id == reference_id:
                return score.order
        return len(self.scores) + 1


def jev_configured() -> bool:
    """Whether the optional ranking layer has a credential to call with."""
    return bool(os.getenv('TYPESAFE_API_KEY', '').strip())


def _truncate(text: str, limit: int = 4000) -> str:
    cleaned = ' '.join(str(text or '').split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + ' …'


def _build_questions(code: str, records: list[dict]):
    """One question per candidate, so each answer maps back to a known reference."""
    from typesafe_sdk import Choice, Noul, Score

    questions = {}
    for index, record in enumerate(records):
        # The reference id is already constrained by ManualRecord to a safe character set,
        # so it can be used as a question key without escaping concerns.
        key = record['reference_id']
        questions[f'{key}__relevance'] = Noul(
            instructions=(f'Does the excerpt below bear on fault code {code} for this machine, '
                          'as opposed to mentioning the code only in passing or in an '
                          'unrelated context?'),
        )
        questions[f'{key}__states_cause'] = Choice(
            instructions='Does the excerpt state a possible cause or a check for this fault?',
            criteria={
                'states_cause': 'The excerpt lists a possible cause, or a check that would find one.',
                'context_only': 'The excerpt is background, a specification, or an unrelated procedure.',
            },
        )
        questions[f'{key}__strength'] = Score(
            instructions='How directly does the excerpt address this fault code?',
            criteria=[
                'Mentions the code without explaining it',
                'Relates to the affected system but not this code',
                'Names the code or its cause explicitly',
            ],
        )
    return questions


def rank_manual_records(code: str, records: list[dict], *, client=None,
                        model: str | None = None) -> Ranking:
    """Rank manual candidates by how directly they address the fault code.

    Never raises for a provider problem: the caller gets `ranked=False` and the
    retrieval order back, because losing the ranking must not lose the analysis.
    """
    if not records:
        return Ranking(ranked=False, method='none', reason='no_candidates')
    if client is None and not jev_configured():
        return Ranking(ranked=False, method='none', reason='not_configured')

    if client is None:
        from typesafe_sdk import TypeSafeClient
        client = TypeSafeClient(api_key=os.environ['TYPESAFE_API_KEY'],
                                model=model or os.getenv('TYPESAFE_MODEL', DEFAULT_MODEL))

    state = {
        'fault_code': code,
        'excerpts': [{'reference_id': record['reference_id'],
                      'section': _truncate(record.get('section'), 300),
                      'text': _truncate(record.get('text'))} for record in records],
    }
    try:
        response = client.system_one(
            state=state,
            questions=_build_questions(code, records),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except BaseException as error:  # noqa: BLE001
        # Deliberately broad. This layer is an optimisation: a provider timeout, an auth
        # failure, a shape this code did not anticipate, or a bug in the SDK must all end
        # as "no ranking" rather than as a failed investigation. The reason is recorded and
        # `ranked` stays False, so a degraded report says so instead of hiding it.
        return Ranking(ranked=False, method='unavailable', reason=type(error).__name__)

    answers = getattr(response, 'answers', None)
    if not isinstance(answers, dict):
        return Ranking(ranked=False, method='unavailable', reason='unexpected_response')

    scores: list[SectionScore] = []
    for record in records:
        key = record['reference_id']
        relevance = answers.get(f'{key}__relevance')
        cause = answers.get(f'{key}__states_cause')
        strength = answers.get(f'{key}__strength')
        if relevance is None or cause is None:
            # An incomplete answer set is reported as unavailable rather than partially
            # applied, so the caller is never left with a half-ranked list.
            return Ranking(ranked=False, method='unavailable', reason='incomplete_answers')
        scores.append(SectionScore(
            reference_id=key,
            relevance=float(getattr(relevance, 'noul', 0.0)),
            confidence=getattr(relevance, 'confidence', None),
            states_cause=getattr(cause, 'choice', None) == 'states_cause',
            strength=float(getattr(strength, 'score', 0.0)) if strength is not None else None,
            order=0,
        ))
    return order_scores(scores)


def order_scores(scores: list[SectionScore]) -> Ranking:
    """Order scores by the rule this project owns, then number them.

    The rule is explicit: relevance first, then whether a cause is stated, then the
    strength score. Ties keep the retrieval order, which is stable for the same input.
    """
    def sort_key(item: tuple[int, SectionScore]):
        original_index, score = item
        return (-score.relevance, 0 if score.states_cause else 1, -(score.strength or 0.0), original_index)

    ordered = sorted(enumerate(scores), key=sort_key)
    renumbered = [SectionScore(reference_id=score.reference_id, relevance=score.relevance,
                               confidence=score.confidence, states_cause=score.states_cause,
                               strength=score.strength, order=index + 1)
                  for index, (_, score) in enumerate(ordered)]
    return Ranking(ranked=True, method='jev_system_one', scores=renumbered)


def reorder_records(ranking: Ranking, records: list[dict]) -> list[dict]:
    """Return the records in the ranking's order; unchanged when nothing was ranked."""
    if not ranking.ranked:
        return list(records)
    by_id = {record['reference_id']: record for record in records}
    ordered = [by_id[score.reference_id] for score in sorted(ranking.scores, key=lambda s: s.order)
               if score.reference_id in by_id]
    # Anything the model did not score keeps its original relative position at the end.
    seen = {item['reference_id'] for item in ordered}
    ordered.extend(record for record in records if record['reference_id'] not in seen)
    return ordered


def describe(ranking: Ranking) -> dict:
    """A JSON-safe summary for the report, so the ranking is visible and auditable."""
    return {
        'ranked': ranking.ranked,
        'method': ranking.method,
        'reason': ranking.reason,
        'relevance_floor': RELEVANCE_FLOOR,
        'sections': [{'reference_id': score.reference_id, 'order': score.order,
                      'relevance': round(score.relevance, 4),
                      'confidence': score.confidence,
                      'states_cause': score.states_cause,
                      'strength': score.strength,
                      'above_floor': score.passes_floor} for score in
                     sorted(ranking.scores, key=lambda s: s.order)],
    }
