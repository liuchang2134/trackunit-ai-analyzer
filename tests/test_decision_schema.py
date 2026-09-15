from app import local_assistant as agent


def test_dynamic_citation_and_check_enums_stay_out_of_wire_messages(monkeypatch):
    seen={}
    class Response:
        def raise_for_status(self):pass
        def json(self):return {'message':{'content':'{"action":"snapshot"}'}}
    def post(url,**kwargs):seen.update(kwargs['json']);return Response()
    monkeypatch.setattr(agent.httpx,'post',post)
    monkeypatch.setattr(agent,'get_ollama_base_url',lambda:'http://127.0.0.1:11434')
    agent.model_step([{'role':'system','content':'allowed choices',
        '_decision_options':{'evidence_ids':['tool:1:snapshot'],'next_check_ids':['check:snapshot']}}],['snapshot'])
    properties=seen['format']['properties']
    assert set(seen['format']['required'])==set(properties)
    assert properties['evidence_ids']['items']['enum']==['tool:1:snapshot']
    assert properties['next_check_ids']['items']['enum']==['check:snapshot']
    assert seen['messages']==[{'role':'system','content':'allowed choices'}]
    agent.model_step([{'role':'system','content':'no evidence yet','_decision_options':{'evidence_ids':[],'next_check_ids':[]}}],['snapshot'])
    assert seen['format']['properties']['evidence_ids']['maxItems']==0
