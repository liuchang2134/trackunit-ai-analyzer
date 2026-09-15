from app.assistant_prompts import cloud_messages, REPORT_INSTRUCTIONS, ROUTING_INSTRUCTIONS


def test_cloud_routing_preserves_question_controls_and_corrections_without_private_metadata():
    messages = [{'role':'system','content':'base'}, {'role':'user','content':'inspect hydraulic pump'},
                {'role':'system','content':'Required: snapshot, faults. Allowed: faults.',
                 '_decision_options':{'evidence_ids':['tool:1:snapshot']}},
                {'role':'system','content':'Your summary omitted partial coverage.'}]
    wire = cloud_messages(messages, can_finish=False)
    assert wire[0]['content'] == ROUTING_INSTRUCTIONS
    assert wire[1]['content'] == 'inspect hydraulic pump'
    assert wire[2]['content'] == messages[2]['content']
    assert wire[3]['content'] == messages[3]['content']
    assert '_decision_options' not in wire[2]
    assert messages[0]['content'] == 'base'
    final = cloud_messages(messages, can_finish=True)
    assert final[0]['content'] == REPORT_INSTRUCTIONS
    assert final[1:] == wire[1:]
