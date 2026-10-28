"""Protocol and evaluation checkpoint contracts, without provider inference."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import AsyncMock
import pytest

from modelcheck import agent,legacy_v1,evaluation as ev
from modelcheck.app import PROJECT
from modelcheck.data import Problem
from modelcheck.store import Store
import test_agent as controlled

SNAPSHOT=PROJECT/'submission/evaluations/v1/initial'


@pytest.mark.parametrize('config',['A','B'])
def test_host_protocol_precedes_first_request(config,tmp_path):
    async def run():
        store,owner,bid,rid=controlled.setup(tmp_path)
        bridge=await controlled.Bridge(tmp_path).open();turn=0
        async def provider(**request):
            nonlocal turn
            turn+=1
            assert agent.SKILL.read_text() in request['messages'][0]['content']
            assert 'compare_runs' in request['messages'][0]['content']
            if turn==1:return controlled.call('compute_metrics',{'bundle_id':bid,'run_id':'run-1'})
            evidence=json.loads(request['messages'][-1]['content'])
            return controlled.response({'content':json.dumps({'summary':'Measured','findings':[{'statement':'Accuracy is 90%.','evidence_ids':[evidence['evidence_id']]}]})})
        try:
            result=await agent.Reviewer(store,bridge).run(owner,rid,bid,'Inspect',config,completion=provider)
            assert result['status']=='completed'
            assert result['runtime_version']=='v2'
            assert result['protocol']['sha256']==hashlib.sha256(agent.SKILL.read_bytes()).hexdigest()
            assert result['events'][0]['kind']=='protocol_loaded'
            assert result['protocol']['source']=='host'
            assert not any(e.get('tool')=='load_review_protocol' for e in result['events'])
            assert result['usage']['requests']==2 and result['usage']['tool_executions']==2
            assert [e['tool'] for e in result['evidence']]==['compute_metrics']
        finally:await bridge.close()
    asyncio.run(run())


@pytest.mark.parametrize('kind',['missing','unreadable','empty','oversize','invalid_utf8','blank'])
def test_bad_protocol_blocks_before_any_provider_call(kind,tmp_path,monkeypatch):
    path=tmp_path/'protocol.md'
    raw={'empty':b'','oversize':b'a'*4097,'invalid_utf8':b'\xff','blank':b'  \n'}
    if kind in raw:path.write_bytes(raw[kind])
    if kind=='unreadable':
        class Unreadable:
            def open(self,*args):raise PermissionError('unreadable fixture')
        monkeypatch.setattr(agent,'SKILL',Unreadable())
    else:monkeypatch.setattr(agent,'SKILL',path)
    called=AsyncMock(side_effect=AssertionError('Provider must not be reached'))
    monkeypatch.setattr(agent,'provider_models',called)
    async def run():
        store,owner,bid,rid=controlled.setup(tmp_path/'state')
        result=await agent.Reviewer(store,FakeBridge(tmp_path)).run(owner,rid,bid,'Inspect')
        assert result['status']=='failed'
        assert result['error']['code'] in {'protocol_unavailable','protocol_invalid'}
        assert result['usage']['requests']==0 and result['protocol'] is None
        assert not store.list(owner,'action')
    asyncio.run(run());called.assert_not_called()


def test_compaction_retains_protocol_and_latest_complete_round(tmp_path):
    class LargeBridge:
        def schemas(self):return []
        async def call(self,*args):return {'accuracy':.9,'description':'x'*2200}
    async def run():
        store,owner,bid,rid=controlled.setup(tmp_path);turn=0
        async def provider(**request):
            nonlocal turn
            turn+=1
            assert agent.SKILL.read_text() in request['messages'][0]['content']
            if turn<3:return controlled.call('compute_metrics',{'bundle_id':bid,'run_id':'run-1'})
            tool_messages=[m for m in request['messages'] if m['role']=='tool']
            assert len(tool_messages)==1
            evidence=json.loads(tool_messages[-1]['content'])
            return controlled.response({'content':json.dumps({'summary':'Measured','findings':[{'statement':'Measured accuracy.','evidence_ids':[evidence['evidence_id']]}]})})
        result=await agent.Reviewer(store,LargeBridge()).run(owner,rid,bid,'Inspect',completion=provider)
        assert result['status']=='completed',result.get('error')
        assert len(result['evidence'])==2
        assert any(e['kind']=='context_compacted' for e in result['events'])
    # Force compaction after two complete rounds, without truncating the newest one.
    original=agent.CONTEXT_LIMIT;agent.CONTEXT_LIMIT=8500
    try:asyncio.run(run())
    finally:agent.CONTEXT_LIMIT=original


def test_compaction_never_deletes_partial_tool_round():
    messages=[{'role':'system','content':'protocol'},{'role':'user','content':'question'},
      {'role':'assistant','tool_calls':[{'id':'one'},{'id':'two'}]},
      {'role':'tool','tool_call_id':'one','content':'x'*22000}]
    original=copy.deepcopy(messages)
    assert agent.compact_history(messages,[])==0
    assert messages==original


def test_preload_counts_against_tool_execution_budget(tmp_path):
    class TinyBridge:
        def schemas(self):return []
        async def call(self,*args):return {'accuracy':.9}
    async def run():
        store,owner,bid,rid=controlled.setup(tmp_path)
        async def provider(**request):
            calls=[{'id':f'call-{i}','type':'function','function':{'name':'compute_metrics','arguments':json.dumps({'bundle_id':bid,'run_id':'run-1'})}} for i in range(16)]
            return controlled.response({'tool_calls':calls},'tool_calls')
        result=await agent.Reviewer(store,TinyBridge()).run(owner,rid,bid,'Inspect',completion=provider)
        assert result['error']['code']=='tool_budget'
        assert len([e for e in result['events'] if e['kind']=='tool_result'])==15
        assert result['usage']['tool_executions']==16
    asyncio.run(run())


def test_v1_engine_and_historical_evidence_are_unchanged():
    manifest=json.loads((SNAPSHOT/'manifest.json').read_text())
    assert hashlib.sha256(Path(legacy_v1.__file__).read_bytes()).hexdigest()==manifest['src/modelcheck/agent.py']
    for name,digest in manifest.items():
        assert hashlib.sha256((SNAPSHOT/name).read_bytes()).hexdigest()==digest
    imported=json.loads((SNAPSHOT/'submission/progress.json').read_text())
    completed=[r for r in imported['rows'] if r['status']=='completed']
    assert len(completed)==12
    assert sum(r['passed'] for r in completed if r['config']=='A')==6
    assert sum(r['passed'] for r in completed if r['config']=='B')==5
    assert next(r for r in completed if r['task']=='matched-comparison' and r['config']=='B')['passed'] is False


class FakeBridge:
    def __init__(self,root):self.root=root
    async def open(self):return self
    async def close(self):pass
    def schemas(self):return json.loads((SNAPSHOT/'tool_schemas.json').read_text())[:4]


class FakeReviewer:
    calls=0
    def __init__(self,store,bridge):self.store=store
    async def run(self,owner,rid,bid,prompt,config,allow_fallback=False):
        type(self).calls+=1
        assert allow_fallback is False
        outcome={'run_id':'run-1','source':None,'counts':{'tn':18,'fp':2,'fn':2,'tp':18},'accuracy':.9}
        evidence=self.store.evidence(owner,rid,'compute_metrics',outcome)
        return {'status':'completed','events':[{'kind':'tool_call','tool':'compute_metrics'}],
          'evidence':[evidence],'usage':{'requests':2,'input_tokens':100,'output_tokens':100,'actual_cost':0},'served_models':['controlled-test'],'seconds':.1}


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    from modelcheck import app
    project=tmp_path/'project';project.mkdir()
    monkeypatch.setattr(app,'PROJECT',project)
    monkeypatch.setattr(ev,'Bridge',FakeBridge)
    monkeypatch.setattr(legacy_v1,'Reviewer',FakeReviewer)
    monkeypatch.setattr(agent,'Reviewer',FakeReviewer)
    monkeypatch.setenv('MODELCHECK_MODEL',legacy_v1.MODEL)
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    FakeReviewer.calls=0
    return project


def import_original(project):
    shutil.copytree(SNAPSHOT,project/'submission/evaluations/v1/initial')
    source=SNAPSHOT/'submission'
    for path in source.rglob('*'):
        if path.is_file():
            dest=project/'submission'/path.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)


def run_eval(project,**kwargs):
    return asyncio.run(ev.evaluate(['A'],1,1,output=project/'test-run',**kwargs))


def test_missing_key_preserves_original_executions(isolated,monkeypatch):
    import_original(isolated)
    out=isolated/'submission'
    before=json.loads((out/'progress.json').read_text())['rows'][:12]
    narrative=(out/'ERROR_ANALYSIS.md').read_bytes()
    assert asyncio.run(ev.evaluate())==2
    after=json.loads((out/'progress.json').read_text())
    assert after['rows'][:12]==before
    assert all(r['status']=='pending_key' for r in after['rows'][12:])
    assert len(after['provenance']['imported_executions'])==12
    assert (out/'ERROR_ANALYSIS.md').read_bytes()==narrative
    assert json.loads((out/'summary.json').read_text())['results']=={'A':{'attempted':6,'passed':6},'B':{'attempted':6,'passed':5}}
    assert FakeReviewer.calls==0
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=5))
    assert asyncio.run(ev.evaluate())==2
    resumed=json.loads((out/'progress.json').read_text())
    assert resumed['rows'][:12]==before
    assert all(row['status']=='pending_quota' for row in resumed['rows'][12:])
    assert FakeReviewer.calls==0


def test_incompatible_configuration_does_not_overwrite(isolated,monkeypatch):
    assert run_eval(isolated)==2
    before={p.name:p.read_bytes() for p in (isolated/'test-run').iterdir() if p.is_file()}
    monkeypatch.setenv('MODELCHECK_MODEL','different-model:free')
    with pytest.raises(Problem,match='fingerprint differs'):run_eval(isolated)
    assert before=={p.name:p.read_bytes() for p in (isolated/'test-run').iterdir() if p.is_file()}


@pytest.mark.parametrize('remaining',[None,0,5,12])
def test_quota_reserve_prevents_inference(isolated,monkeypatch,remaining):
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=remaining))
    assert run_eval(isolated)==2
    assert FakeReviewer.calls==0
    summary=json.loads((isolated/'test-run/summary.json').read_text())
    assert summary['attempted']==0 and summary['pending']==1


def test_exact_quota_threshold_and_repeated_run_are_safe(isolated,monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=13))
    assert run_eval(isolated)==0
    assert FakeReviewer.calls==1
    trace=isolated/'test-run/traces/metrics-A.json';before=trace.read_bytes()
    assert run_eval(isolated)==0
    assert trace.read_bytes()==before and FakeReviewer.calls==1


def test_interrupted_progress_recovers_trace_without_repeat(isolated,monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=13))
    original=ev.atomic_json;writes=0
    def interrupt(path,value):
        nonlocal writes
        if Path(path).name=='progress.json':
            writes+=1
            if writes==2:raise OSError('simulated interrupted checkpoint')
        original(path,value)
    monkeypatch.setattr(ev,'atomic_json',interrupt)
    with pytest.raises(OSError,match='interrupted'):run_eval(isolated)
    assert FakeReviewer.calls==1
    assert (isolated/'test-run/traces/metrics-A.json').exists()
    monkeypatch.setattr(ev,'atomic_json',original)
    assert run_eval(isolated)==0
    assert FakeReviewer.calls==1


def test_changed_trace_is_rejected(isolated,monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=13));assert run_eval(isolated)==0
    path=isolated/'test-run/traces/metrics-A.json';path.write_text(path.read_text()+' ')
    with pytest.raises(Problem,match='checksum changed'):run_eval(isolated)
    assert FakeReviewer.calls==1


def test_atomic_replace_failure_keeps_previous_file(tmp_path,monkeypatch):
    path=tmp_path/'progress.json';path.write_text('original')
    def fail(*args):raise OSError('simulated replace failure')
    with monkeypatch.context() as context:
        context.setattr(ev.os,'replace',fail)
        with pytest.raises(OSError):ev.atomic_write(path,'new')
    assert path.read_text()=='original'
    assert list(tmp_path.iterdir())==[path]


def test_smoke_isolation_and_v2_priority(isolated,monkeypatch):
    root=isolated/'submission';root.mkdir();(root/'progress.json').write_text('capstone sentinel')
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    quota=AsyncMock(side_effect=AssertionError('v2 quota must not be used before v1 completes'))
    monkeypatch.setattr(ev,'quota',quota)
    assert asyncio.run(ev.smoke())==2
    assert (root/'progress.json').read_text()=='capstone sentinel'
    paths=list((isolated/'runtime/smoke').glob('*/summary.json'))
    assert len(paths)==1
    assert json.loads(paths[0].read_text())['stop_reason']=='v1_incomplete'
    assert FakeReviewer.calls==0;quota.assert_not_called()


def test_runtime_selection_and_v2_output_boundary(isolated,monkeypatch):
    import_original(isolated)
    progress=isolated/'submission/progress.json';saved=json.loads(progress.read_text())
    saved['trace_hashes']={}
    for row in saved['rows']:
        trace=f"traces/{row['task']}-{row['config']}.json"
        path=isolated/'submission'/trace
        if not path.exists():path.write_text('{}')
        row.update(status='completed',passed=True,trace=trace)
        saved['trace_hashes'][trace]=ev.sha(path.read_bytes())
    progress.write_text(json.dumps(saved))
    assert ev.baseline_complete(isolated)
    original=(isolated/'submission/traces/metrics-A.json').read_bytes()
    (isolated/'submission/traces/metrics-A.json').write_bytes(original+b' ')
    assert not ev.baseline_complete(isolated)
    (isolated/'submission/traces/metrics-A.json').write_bytes(original)
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=13))
    class WrongReviewer:
        def __init__(self,*args):raise AssertionError('v1 selected for a v2 run')
    monkeypatch.setattr(legacy_v1,'Reviewer',WrongReviewer)
    assert run_eval(isolated,runtime_version='v2')==0
    assert FakeReviewer.calls==1
    assert json.loads((isolated/'test-run/metadata.json').read_text())['runtime_version']=='v2'
    with pytest.raises(Problem,match='v2 cannot write'):
        asyncio.run(ev.evaluate(runtime_version='v2',output=isolated/'submission'))


def test_priority_does_not_change_task_definitions():
    rows=[{'task':t['id'],'config':'A','status':'pending_quota'} for t in ev.TASKS]
    assert [r['task'] for r in ev.execution_order(rows,'v1')][:5]==ev.PRIORITY
    assert ev.execution_order(rows,'v2')[0]['task']=='matched-comparison'
    assert json.loads((SNAPSHOT/'configuration.json').read_text())['suite_sha256']==ev.data.digest(ev.TASKS)


def test_snapshot_cannot_be_selected_as_output(isolated):
    target=isolated/'submission/evaluations/v1/initial'
    with pytest.raises(Problem,match='immutable'):
        asyncio.run(ev.evaluate(['A'],1,1,output=target))
    assert not target.exists()


def test_review_api_version_metadata(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from modelcheck.app import create_app
    monkeypatch.setattr('modelcheck.app.load_dotenv',lambda *a,**kw:None)
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    with TestClient(create_app(tmp_path)) as client:
        token=client.post('/api/sessions',json={}).json()['token'];headers={'Authorization':'Bearer '+token}
        assert client.get('/healthz').json()['runtime_version']=='v2'
        replay=client.post('/api/replays/comparison',headers=headers,json={}).json()
        assert replay['runtime_version']=='v1' and replay['protocol']['source']=='model'
        assert replay['protocol']['sha256'] is None
        imported=client.post('/api/bundles',headers=headers,json={'sample_id':'comparison'}).json()
        result=client.post('/api/inspections',headers=headers,json={'bundle_id':imported['bundle_id'],'question':'Inspect'}).json()
        assert result['runtime_version']=='v2' and result['protocol'] is None


def test_cli_check_dispatches_to_isolated_smoke(monkeypatch):
    import sys
    from types import SimpleNamespace
    from modelcheck import cli
    monkeypatch.setattr('dotenv.load_dotenv',lambda *a,**k:None)
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(cli.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    smoke=AsyncMock(return_value=2);monkeypatch.setattr(ev,'smoke',smoke)
    monkeypatch.setattr(sys,'argv',['modelcheck','check'])
    with pytest.raises(SystemExit) as exit:cli.main()
    assert exit.value.code==2;smoke.assert_awaited_once_with()


def test_targeted_run_is_separate_from_full_suite(isolated,monkeypatch):
    root=isolated/'submission';root.mkdir();(root/'progress.json').write_text('full-suite sentinel')
    monkeypatch.setenv('OPENROUTER_API_KEY','controlled-test-key')
    monkeypatch.setattr(ev,'quota',AsyncMock(return_value=13))
    assert asyncio.run(ev.evaluate(['B'],task_ids=['metrics']))==0
    assert (root/'progress.json').read_text()=='full-suite sentinel'
    outputs=list((root/'evaluations/v1').glob('*/summary.json'))
    assert len(outputs)==1
    summary=json.loads(outputs[0].read_text())
    assert summary['purpose']=='targeted' and summary['scheduled']==1
    assert json.loads((outputs[0].parent/'tasks.jsonl').read_text())['id']=='metrics'
    assert FakeReviewer.calls==1


@pytest.mark.parametrize('selection,limit',[(['unknown'],None),(['metrics','metrics'],None),(['metrics'],1)])
def test_invalid_targeted_selection_is_rejected(isolated,selection,limit):
    with pytest.raises(Problem,match='unique known task IDs'):
        asyncio.run(ev.evaluate(task_ids=selection,limit=limit))
    assert not (isolated/'submission').exists()
