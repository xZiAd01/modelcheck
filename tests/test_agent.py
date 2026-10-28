"""Controlled provider tests are contract tests, never reported as live evals."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from openai.types.chat import ChatCompletion

from modelcheck.agent import Reviewer
from modelcheck.bridge import Bridge
from modelcheck.store import Store
from modelcheck import samples

def response(message,reason='stop'):
    return ChatCompletion.model_validate({'id':'test','created':0,'model':'controlled-test-adapter',
      'object':'chat.completion','choices':[{'index':0,'finish_reason':reason,'message':{'role':'assistant',**message}}],
      'usage':{'prompt_tokens':100,'completion_tokens':100,'total_tokens':200}})

def call(name,args):
    return response({'tool_calls':[{'id':'call-1','type':'function','function':{'name':name,'arguments':json.dumps(args)}}]},'tool_calls')

def setup(tmp_path):
    s=Store(tmp_path);owner,_=s.session();bid=s.put(owner,'bundle',samples.bundle());rid=s.put(owner,'review',{'status':'queued','bundle_id':bid,'mode':'controlled-test'})
    return s,owner,bid,rid

def test_real_mcp_review_and_citations(tmp_path):
    async def run():
        s,owner,bid,rid=setup(tmp_path);bridge=await Bridge(tmp_path).open();turn=0
        async def provider(**req):
            nonlocal turn
            turn+=1
            if turn==1:return call('compute_metrics',{'bundle_id':bid,'run_id':'run-1'})
            evidence=json.loads(req['messages'][-1]['content'])
            return response({'content':json.dumps({'summary':'Baseline measured.','findings':[{'statement':'Baseline accuracy is 90%.','evidence_ids':[evidence['evidence_id']]}],'limitations':['Controlled contract test.']})})
        try:
            result=await Reviewer(s,bridge).run(owner,rid,bid,'Check metrics.',completion=provider)
            assert result['status']=='completed',result.get('error')
            assert result['usage']['requests']==2
            assert result['evidence'][0]['result']['accuracy']==.9
        finally:await bridge.close()
    asyncio.run(run())

def test_truncated_response_cannot_execute_write(tmp_path):
    async def run():
        s,owner,bid,rid=setup(tmp_path);bridge=await Bridge(tmp_path).open()
        async def provider(**req):
            return response({'tool_calls':[{'id':'bad','type':'function','function':{'name':'save_experiment_spec','arguments':'{"path":"../../stolen.json"'}}]},'length')
        try:
            result=await Reviewer(s,bridge).run(owner,rid,bid,'Attack',completion=provider)
            assert result['status']=='failed' and result['error']['code']=='truncated_reply'
            assert not s.list(owner,'action')
            assert not list(tmp_path.rglob('*.json'))
        finally:await bridge.close()
    asyncio.run(run())

def test_unknown_evidence_repair_still_fails(tmp_path):
    async def run():
        s,owner,bid,rid=setup(tmp_path);bridge=await Bridge(tmp_path).open()
        async def provider(**req):
            return response({'content':json.dumps({'summary':'Unsupported','findings':[{'statement':'Invented','evidence_ids':['e_invented']}],'limitations':[]})})
        try:
            result=await Reviewer(s,bridge).run(owner,rid,bid,'Check',completion=provider)
            assert result['status']=='failed' and result['error']['code']=='invalid_report'
            assert result['usage']['requests']==2
        finally:await bridge.close()
    asyncio.run(run())

def test_bridge_blocks_cross_bundle_and_owner_override(tmp_path):
    async def run():
        from modelcheck.data import Problem
        s,owner,bid,rid=setup(tmp_path);bridge=await Bridge(tmp_path).open()
        try:
            with pytest.raises(Problem):await bridge.call('inspect_manifest',{'bundle_id':'other'},owner,bid)
            with pytest.raises(Problem):await bridge.call('inspect_manifest',{'bundle_id':bid,'owner':'fake'},owner,bid)
        finally:await bridge.close()
    asyncio.run(run())
