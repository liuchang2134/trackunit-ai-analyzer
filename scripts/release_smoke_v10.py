"""Exercise a fresh extracted v10 copy, writing only synthetic local state; no provider network."""
import ipaddress
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_smoke import run as previous_checks
from scripts.verify_release_v10 import verify_folder


def run():
 os.environ.pop('XGSS_CONFIG_PATH',None)
 attempts=[];connect_before=socket.socket.connect;resolve_before=socket.getaddrinfo
 def local(host):
  if host=='localhost':return True
  try:return ipaddress.ip_address(host).is_loopback
  except ValueError:return False
 def connect(sock,address):
  if isinstance(address,tuple) and not local(address[0]):
   attempts.append('nonlocal socket');raise RuntimeError('Provider network disabled during release verification')
  return connect_before(sock,address)
 def resolve(host,*args,**kwargs):
  if host is not None and not local(host):
   attempts.append('nonlocal DNS');raise RuntimeError('Provider network disabled during release verification')
  return resolve_before(host,*args,**kwargs)
 socket.socket.connect=connect;socket.getaddrinfo=resolve
 try:
  result=previous_checks(verifier=verify_folder)
  from fastapi.testclient import TestClient
  from app.main import app
  with TestClient(app) as client:
   for name in ('platform-context.js','local-drafts.js','maintenance-cases.js','xgss-viewer.js'):
    assert client.get('/assistant-ui/'+name).status_code==200
   evaluation=client.get('/assistant/cooling/evaluation').json()['extended']
   assert evaluation['status']=='available' and evaluation['candidate_adopted'] is False
   metrics=evaluation['reports']['original']['overall']
   assert (metrics['episodes'],metrics['detected_events'],metrics['events'])==(96,28,31)
   device=next(d for d in client.get('/assistant/device-index').json()['devices'] if d['machine_id']=='SIM-PARTS-REPLAY-001')
   scope={key:device[key] for key in ('machine_id','dataset_id','source')}
   assert client.get('/assistant/draft',params=scope).json()['draft'] is None
   content={'question':'检查模拟告警与资料','observations':'仅为安装自检，尚未维修。','task':'parts','language':'zh','prior_record_id':None}
   draft=client.put('/assistant/draft',json={**scope,'expected_revision':None,'content':content})
   assert draft.status_code==200
   assert client.get('/assistant/draft',params=scope).json()['draft']['content']==content
   assert client.put('/assistant/draft',json={**scope,'expected_revision':None,'content':content}).status_code==409
   created=client.post('/assistant/cases',json={**scope,'title':'安装自检：模拟排查','note':'仅核对本机记录功能。'})
   assert created.status_code==200 and created.json()['created'];case=created.json()['case']
   for state in ('in_progress','waiting','archived'):
    response=client.post('/assistant/cases/'+case['case_id']+'/events',json={
     'expected_revision':case['revision'],'state':state,'note':'模拟记录：保留原始观察，未确认维修。'})
    assert response.status_code==200;case=response.json()['case']
   assert case['revision']==4 and len(case['events'])==4
   assert client.get('/assistant/cases?state=archived').json()['total']==1
   exported=client.get('/assistant/cases/'+case['case_id']+'/export.md')
   assert exported.status_code==200 and '模拟记录：保留原始观察，未确认维修。' in exported.text
   assert '不代表设备已修复' in exported.text
   xgss=client.get('/assistant/xgss/status').json()
   assert not xgss['catalog_ready'] and not xgss['fault_ready'] and not xgss['live_verified']
   denied=client.post('/assistant/xgss/open',json={
    'machine_id':device['machine_id'],'dataset_id':device['dataset_id'],
    'vin':device['serial_number'],'vin_confirmed':True,'fault_code':'E4030','language':'zh'})
   assert denied.status_code in (404,422)
  assert not attempts;verify_folder(ROOT)
  result.update(extension_version='0.4.0',expanded_evaluation_available=True,
   draft_roundtrip_and_stale_conflict=True,maintenance_history_archive_export=True,
   unconfigured_xgss_disabled=True,synthetic_xgss_production_request_rejected=True,
   additional_provider_network_attempts=len(attempts),installed_chrome_verified=False)
  return result
 finally:
  socket.socket.connect=connect_before;socket.getaddrinfo=resolve_before


if __name__=='__main__':
 print(json.dumps(run(),ensure_ascii=False,indent=2))
