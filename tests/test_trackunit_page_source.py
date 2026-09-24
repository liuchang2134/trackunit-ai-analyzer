"""Visible browser-page faults retain distinct provenance from the event API."""
from app import xgss_research_ai as ai


def test_visible_page_fault_source_is_accepted_and_bounded():
    symptom = ai.Symptom(
        symptom='Trackunit 当前 Events 页可见故障：SPN 2664 / FMI 3；描述：Joystick voltage above normal。',
        symptom_source='trackunit_page',
    )
    assert symptom.symptom_source == 'trackunit_page'
    instructions = ai._symptom_source_instructions(symptom.symptom_source)
    assert '当前 Trackunit Events 页可见卡片' in instructions
    assert '未通过故障 API 核验完整事件' in instructions
