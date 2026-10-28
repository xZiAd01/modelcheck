import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score

from modelcheck import data,samples
from modelcheck.app import create_app
from modelcheck.store import Store

def test_metrics_independently_against_sklearn():
    b=samples.bundle()
    for run in b['runs']:
        actual=[r['label'] for r in b['manifest']]
        predicted=[r['predicted_label'] for r in run['predictions']]
        got=data.metrics(b,run['id'])
        assert got['accuracy']==accuracy_score(actual,predicted)
        assert got['precision']==precision_score(actual,predicted)
        assert got['recall']==recall_score(actual,predicted)
        assert got['f1']==f1_score(actual,predicted)
    assert data.metrics(b,'run-1')['counts']=={'tn':18,'fp':2,'fn':2,'tp':18}
    assert data.metrics(b,'run-2')['counts']=={'tn':19,'fp':1,'fn':5,'tp':15}

def test_comparison_slices_and_coverage():
    b=samples.bundle();c=data.compare(b)
    assert c['deltas']['accuracy']==pytest.approx(-.05)
    web=next(s for s in c['slices'] if s['source']=='web')
    assert web['baseline']['recall']==.9 and web['candidate']['recall']==.5
    partial=samples.bundle('partial')
    assert data.metrics(partial,'run-2')['population']=='available predictions only'
    with pytest.raises(data.Problem,match='entire same'):data.compare(partial)

@pytest.mark.parametrize('field,code',[('sample_id','sample_overlap'),('group_id','group_overlap'),('content_hash','hash_overlap')])
def test_overlap(field,code):
    result=data.inspect(samples.bundle('overlap'))
    assert code in {f['code'] for f in result['findings']}

def test_duplicates_and_conflicts_quarantined():
    b=samples.bundle();b['manifest'].append(dict(b['manifest'][0]))
    assert data.inspect(b)['status']=='quarantined'
    with pytest.raises(data.Problem):data.metrics(b,'run-1')
    b=samples.bundle();b['manifest'].append({**b['manifest'][0],'split':'train','label':1})
    assert 'conflicting_labels' in {f['code'] for f in data.inspect(b)['findings']}

@pytest.mark.parametrize('score',['nan','inf','1.1','-0.1','word'])
def test_invalid_scores(score):
    with pytest.raises(data.Problem):data.parse_csv(f'sample_id,predicted_label,score\na,1,{score}\n',{'sample_id','predicted_label'},'predictions')

def test_undefined_and_malformed_inputs():
    b=samples.bundle()
    for row in b['manifest']:row['label']=0
    for run in b['runs']:
        for row in run['predictions']:row['predicted_label']=0
    m=data.metrics(b,'run-1');assert m['accuracy']==1 and m['recall'] is None and m['precision'] is None
    for text in ['', 'sample_id,label\na,0\n','sample_id,split,source,label\na,test,x,3\n']:
        with pytest.raises(data.Problem):data.build_bundle(text,['sample_id,predicted_label\na,0\n'])

def proposal(store,owner):
    bid=store.put(owner,'bundle',samples.bundle());rid=store.put(owner,'review',{})
    ev=store.evidence(owner,rid,'compute_metrics',{'accuracy':.9})
    spec={'objective':'Investigate errors','change':'Use a less aggressive quantization setting',
          'selection_rule':'Select using validation data only','success_criterion':'Improve validation recall',
          'run_ids':['run-1'],'evidence_ids':[ev['evidence_id']]}
    return store.propose(owner,rid,bid,spec),spec

def test_approval_exact_idempotent_and_reject(tmp_path):
    s=Store(tmp_path);owner,_=s.session();a,_=proposal(s,owner)
    assert not list(tmp_path.rglob('*.json'))
    with pytest.raises(data.Problem):s.decide(owner,a['id'],True,'0'*64)
    saved=s.decide(owner,a['id'],True,a['digest']);s.decide(owner,a['id'],True,a['digest'])
    assert saved['status']=='saved' and len(list(tmp_path.rglob('*.json')))==1
    second,_=proposal(s,owner);s.decide(owner,second['id'],False,second['digest'])
    with pytest.raises(data.Problem):s.decide(owner,second['id'],True,second['digest'])
    assert len(list(tmp_path.rglob('*.json')))==1

def test_proposal_path_injection_foreign_and_expiry(tmp_path):
    from pydantic import ValidationError
    s=Store(tmp_path);owner,_=s.session();a,spec=proposal(s,owner)
    with pytest.raises(ValidationError):s.propose(owner,a['review_id'],a['bundle_id'],{**spec,'path':'../../stolen.json'})
    other,_=s.session()
    with pytest.raises(data.Problem):s.decide(other,a['id'],True,a['digest'])
    a['expires']=time.time()-1;s.put(owner,'action',a,a['id'])
    with pytest.raises(data.Problem,match='expired'):s.decide(owner,a['id'],True,a['digest'])
    assert not (tmp_path.parent/'stolen.json').exists()

def test_reset_clears_saved_files_and_access(tmp_path):
    s=Store(tmp_path);owner,token=s.session();a,_=proposal(s,owner);s.decide(owner,a['id'],True,a['digest']);s.reset(owner)
    assert not list(tmp_path.rglob('*.json'))
    with pytest.raises(data.Problem):s.owner(token)

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setattr('modelcheck.app.load_dotenv',lambda *a,**kw:None)
    with TestClient(create_app(tmp_path)) as c:yield c

def auth(client):
    return {'Authorization':'Bearer '+client.post('/api/sessions',json={}).json()['token']}

def test_api_mcp_import_inspection_and_cross_session(client):
    h=auth(client);h2=auth(client)
    assert client.get('/healthz').json()['mcp_ready']
    b=client.post('/api/bundles',headers=h,json={'sample_id':'comparison'}).json()
    req={'bundle_id':b['bundle_id'],'question':'Inspect'}
    r=client.post('/api/inspections',headers=h,json=req)
    assert r.status_code==200,r.text
    result=r.json();assert result['mode']=='deterministic'
    assert {e['tool'] for e in result['evidence']}=={'inspect_manifest','compute_metrics','compare_runs'}
    assert client.get('/api/reviews/'+result['id'],headers=h2).status_code==404
    assert client.post('/api/inspections',headers=h2,json=req).status_code==404
    assert client.get('/api/reviews/'+result['id']).status_code==401

def test_upload_and_api_approval(client):
    h=auth(client)
    b=client.post('/api/bundles',headers=h,json=samples.files()).json()
    r=client.post('/api/inspections',headers=h,json={'bundle_id':b['bundle_id'],'question':'Inspect'}).json()
    spec={'objective':'Investigate web errors','change':'Try a higher precision quantization setting',
        'selection_rule':'Choose on validation only','success_criterion':'Improve validation recall',
        'run_ids':['run-1'],'evidence_ids':[r['evidence'][0]['evidence_id']]}
    a=client.post('/api/proposals',headers=h,json={'review_id':r['id'],'spec':spec}).json()
    out=client.post('/api/actions/'+a['id']+'/decision',headers=h,json={'approved':True,'digest':a['digest']})
    assert out.status_code==200,out.text
    assert client.get('/api/actions/'+a['id']+'/download',headers=h).status_code==200
    exported=client.get('/api/reviews/'+r['id']+'/export',headers=h).json()
    assert exported['pending_action']['status']=='saved'

def test_api_guards(client):
    assert client.post('/api/sessions',json={},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/sessions',content='{}').status_code==415
    assert client.post('/api/sessions',content='x'*(4*1024*1024+1),headers={'Content-Type':'application/json'}).status_code==413
    h=auth(client)
    assert client.post('/api/bundles',headers=h,json={'manifest_csv':'bad','predictions':['bad']}).status_code==422
    assert client.post('/api/reviews',headers=h,json={'bundle_id':'missing','question':'Inspect'}).status_code==503

def test_recorded_replay_is_honest_and_session_scoped(client):
    h=auth(client)
    r=client.post('/api/replays/comparison',headers=h,json={})
    assert r.status_code==200,r.text
    x=r.json()
    assert x['mode']=='recorded' and 'No model request' in x['report']['summary']
    assert 'cannot establish' in x['application_notice']
    assert any(e['tool']=='compare_runs' for e in x['evidence'])
    assert x['pending_action'] is None
    assert client.get('/api/reviews/'+x['id'],headers=auth(client)).status_code==404

def test_all_final_fixtures_and_live_grader_expectations():
    from modelcheck.evaluation import TASKS,fixture
    assert len(TASKS)==18 and len({t['id'] for t in TASKS})==18
    for task in TASKS:
        b=fixture(task);v=data.inspect(b)
        if task.get('issue'):assert task['issue'] in {f['code'] for f in v['findings']}
        if task.get('metric'):
            m=data.metrics(b,task['metric']['run_id'])
            assert all(m.get(k)==val for k,val in task['metric'].items())

