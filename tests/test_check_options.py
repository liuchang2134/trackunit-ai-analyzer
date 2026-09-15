from app.check_options import build_check_options


def test_catalog_procedure_is_verbatim_and_attributed():
    evidence={'catalog:DEMO-P':{'checks':['核对对应维修手册。'], 'provenance':'demo',
        'source_document':'演示目录', 'source_page':'1', 'revision':'v1'}}
    choices=build_check_options(evidence)
    assert choices[0]['text']=='核对对应维修手册。'
    assert choices[0]['evidence_ids']==['catalog:DEMO-P']
    assert choices[0]['source_document']=='演示目录 / 1 / v1'
    assert choices[0]['provenance']=='demo'


def test_missing_data_produces_data_requests_not_repair_procedures():
    evidence={'tool:1:snapshot':{'source':'imported_synthetic'},
        'tool:2:trends':{'operating_hours_delta':None,'idle_share':None},
        'tool:3:parts':{'candidates':[]}}
    choices=build_check_options(evidence)
    assert {c['check_id'] for c in choices}=={'check:snapshot','check:trend-coverage','check:catalog-gap'}
    assert '回放' in choices[0]['text']
    assert all(set(c['evidence_ids'])<=set(evidence) for c in choices)
    assert all(c['provenance']=='application_rule' for c in choices)
    assert 'replay' in build_check_options(evidence,'en')[0]['text']


def test_no_catalog_check_without_matching_catalog_evidence():
    assert build_check_options({'tool:1:parts':{'candidates':[]}})[0]['check_id']=='check:catalog-gap'
    assert build_check_options({})==[]
