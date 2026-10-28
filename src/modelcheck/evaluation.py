"""Versioned evaluation, atomic checkpoints and quota-aware live execution."""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
import csv
from datetime import datetime,timezone
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import tempfile
import uuid
import httpx

from . import data,agent,legacy_v1
from .baseline import TASKS,fixture,grade
from .store import Store
from .bridge import Bridge

PENDING={'pending_quota','pending_key','pending_baseline'}
PRIORITY=['malicious-metadata','forbidden-destination','rejected-save','approved-save','idempotent-save']
FIELDS=['task','config','trial','status','passed','failed_checks','requests','input_tokens','output_tokens','actual_cost','seconds','trace']


def sha(raw):return hashlib.sha256(raw).hexdigest()

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def atomic_write(path,content):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=content.encode() if isinstance(content,str) else content
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name+'.',suffix='.tmp',delete=False) as f:
            temporary=Path(f.name);f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def atomic_json(path,value):atomic_write(path,json.dumps(value,indent=2,ensure_ascii=False)+'\n')


@contextmanager
def run_lock(project,out):
    # Advisory locks are released by the OS after an interrupted process.
    import fcntl
    Path(out).mkdir(parents=True,exist_ok=True)
    with (Path(out)/'.evaluation.lock').open('a') as handle:
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise data.Problem('evaluation_busy','This evaluation directory is already in use',409) from exc
        try:yield
        finally:fcntl.flock(handle,fcntl.LOCK_UN)


def fingerprint(runtime_version,schemas,tasks,configs,model):
    module={'v1':legacy_v1,'v2':agent}[runtime_version]
    package=Path(__file__).parent;project=package.parents[1]
    components={'reviewer':sha(Path(module.__file__).read_bytes()),
      'protocol':sha(module.SKILL.read_bytes()),'graders':sha(inspect.getsource(grade).strip().encode()),
      'fixtures':sha(inspect.getsource(fixture).strip().encode()),'tools':sha(canonical(schemas)),
      'prompts':sha(canonical({'A':module.SYSTEM,'B':module.SYSTEM+'\n'+module.DELTA})),
      'dependencies':sha((project/'uv.lock').read_bytes()),'project':sha((project/'pyproject.toml').read_bytes())}
    for name in ['data.py','store.py','bridge.py','mcp_server.py','samples.py']:
        components[name]=sha((package/name).read_bytes())
    identity={'runtime_version':runtime_version,'suite_version':'1','suite_hash':data.digest(tasks),
      'configs':list(configs),'model':model,'trials':1,'components':components}
    return {**identity,'fingerprint':sha(canonical(identity))}


def verify_v1_source(schemas):
    package=Path(__file__).parent;project=package.parents[1]
    snapshot=project/'submission/evaluations/v1/initial'
    config=json.loads((snapshot/'configuration.json').read_text())
    manifest=json.loads((snapshot/'manifest.json').read_text())
    pairs=[(package/'legacy_v1.py','src/modelcheck/agent.py')]
    pairs += [(package/name,'src/modelcheck/'+name) for name in ['data.py','store.py','bridge.py','mcp_server.py','samples.py']]
    pairs += [(legacy_v1.SKILL,'src/modelcheck/skills/review-experiment/SKILL.md'),(project/'uv.lock','uv.lock'),(project/'pyproject.toml','pyproject.toml')]
    valid=all(sha(path.read_bytes())==manifest[key] for path,key in pairs)
    valid=valid and sha(inspect.getsource(grade).strip().encode())==config['grader_sha256']
    valid=valid and data.digest(TASKS)==config['suite_sha256'] and sha(canonical(schemas))==config['tool_schemas_sha256']
    original=(snapshot/'src/modelcheck/evaluation.py').read_text()
    import ast
    source_fixture=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef) and n.name=='fixture')
    valid=valid and inspect.getsource(fixture).strip()==ast.get_source_segment(original,source_fixture).strip()
    if not valid:raise data.Problem('baseline_drift','The v1 reviewer, tools, protocol, dependencies or graders differ from the frozen release',409)


def baseline_complete(project):
    try:
        saved=json.loads((Path(project)/'submission/progress.json').read_text())
        expected={(t['id'],c) for t in TASKS for c in ['A','B']}
        complete=(saved['meta'].get('runtime_version','v1')=='v1' and saved['meta']['suite_hash']==data.digest(TASKS)
          and saved['meta']['configs']==['A','B'] and len(saved['rows'])==len(expected)
          and {(r['task'],r['config']) for r in saved['rows']}==expected
          and all(r['status'] not in PENDING and r['trial']==0 and isinstance(r['passed'],bool) for r in saved['rows']))
        if not complete:return False
        for row in saved['rows']:
            trace=f"traces/{row['task']}-{row['config']}.json"
            if row.get('trace')!=trace or saved.get('trace_hashes',{}).get(trace)!=sha((Path(project)/'submission'/trace).read_bytes()):return False
        return True
    except (OSError,ValueError,KeyError,TypeError):return False


def prepare(out,meta,tasks,project):
    progress=out/'progress.json'
    saved=json.loads(progress.read_text()) if progress.exists() else None
    imports=[]
    if saved:
        if 'fingerprint' not in saved['meta']:
            snapshot=Path(project)/'submission/evaluations/v1/initial'
            original=json.loads((snapshot/'submission/progress.json').read_text())
            if out.resolve()!=(Path(project)/'submission').resolve() or meta['runtime_version']!='v1' or saved!=original:
                raise data.Problem('evaluation_mismatch','Unversioned progress does not match the original v1 snapshot',409)
            old_meta={k:meta[k] for k in original['meta']}
            if old_meta!=original['meta']:raise data.Problem('evaluation_mismatch','Evaluation configuration differs; select a new output directory',409)
            imports=json.loads((snapshot/'imports.json').read_text())['executions']
        elif saved['meta']!=meta:
            raise data.Problem('evaluation_mismatch','Evaluation fingerprint differs; select a new output directory',409)
    expected={(t['id'],c) for t in tasks for c in meta['configs']}
    previous={(r['task'],r['config']):r for r in saved['rows']} if saved else {}
    if saved and (set(previous)!=expected or len(previous)!=len(saved['rows']) or any(r['trial']!=0 for r in saved['rows'])):
        raise data.Problem('invalid_checkpoint','Evaluation rows do not match the selected tasks and configurations',409)
    rows=[previous.get((t['id'],c),{'task':t['id'],'config':c,'trial':0,'status':'pending_quota','passed':'','failed_checks':'not run','requests':0,'input_tokens':0,'output_tokens':0,'actual_cost':'','seconds':'','trace':''}) for t in tasks for c in meta['configs']]
    hashes=dict(saved.get('trace_hashes',{})) if saved else {}
    for item in imports:hashes[item['trace']]=item['sha256']
    for row in rows:
        path=out/f"traces/{row['task']}-{row['config']}.json"
        if row['status'] not in PENDING:
            if not row['trace'] or Path(row['trace']).as_posix()!=path.relative_to(out).as_posix() or not isinstance(row['passed'],bool):
                raise data.Problem('invalid_checkpoint','Executed row has no valid outcome or trace',409)
            if not path.is_file() or hashes.get(row['trace'])!=sha(path.read_bytes()):
                raise data.Problem('invalid_checkpoint','Executed trace is missing or its checksum changed',409)
        elif path.exists():
            checkpoint=json.loads(path.read_text())
            recovered=checkpoint.get('row',{})
            if (checkpoint.get('fingerprint')!=meta['fingerprint'] or recovered.get('task')!=row['task']
              or recovered.get('config')!=row['config'] or recovered.get('trial')!=0
              or recovered.get('status') in PENDING or not isinstance(recovered.get('passed'),bool)
              or recovered.get('trace')!=path.relative_to(out).as_posix()):
                raise data.Problem('invalid_checkpoint','Uncommitted trace cannot be safely recovered',409)
            row.update(recovered);hashes[row['trace']]=sha(path.read_bytes())
    state={'meta':meta,'rows':rows,'trace_hashes':hashes}
    if saved and saved.get('provenance'):state['provenance']=saved['provenance']
    elif imports:state['provenance']={'imported_executions':imports,'metadata_origin':'Historical traces imported unchanged. Runtime fingerprints recovered from the published v1 source; not recorded during those executions.'}
    return state


async def quota():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response=await client.get('https://openrouter.ai/api/v1/key',headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY']})
            response.raise_for_status()
            payload=response.json()
            account=payload.get('data') if isinstance(payload,dict) else None
            allowance=account.get('free_model_daily_requests') if isinstance(account,dict) else None
            remaining=allowance.get('remaining') if isinstance(allowance,dict) else None
            return remaining if type(remaining) is int and remaining>=0 else None
    except (httpx.HTTPError,KeyError,ValueError,TypeError):return None


def write_outputs(out,rows,meta,stop_reason=None):
    for name,selected in [('evaluation.csv',rows)]+[(f'{c}.csv',[r for r in rows if r['config']==c]) for c in meta['configs']]:
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=FIELDS)
        writer.writeheader();writer.writerows(selected);atomic_write(out/name,buffer.getvalue())
    attempted=[r for r in rows if r['status'] not in PENDING]
    summary={**meta,'scheduled':len(rows),'attempted':len(attempted),'pending':len(rows)-len(attempted),
      'results':{c:{'attempted':sum(r['config']==c for r in attempted),'passed':sum(r['config']==c and r['passed'] is True for r in attempted)} for c in meta['configs']},
      'stop_reason':stop_reason,'limitation':'One fresh trial per task. Pending rows are not executed evaluations; results are specific to the recorded runtime version and fingerprint.'}
    atomic_json(out/'summary.json',summary)
    lines=[f"# {meta['runtime_version']} evaluation coverage",'',f"Executed {len(attempted)} of {len(rows)} reviews; {summary['pending']} remain pending.",'',f"Stop reason: {stop_reason or 'complete'}.",'','Reserve policy: start a review only with at least 13 requests remaining (eight maximum plus five for the demo). This policy does not guarantee the provider has requests available.','', '| Configuration | Executed | Passed |','|---|---:|---:|']
    for c,result in summary['results'].items():lines.append(f"| {c} | {result['attempted']} | {result['passed']} |")
    lines+=['','## Failures and pending coverage','']+[f"- {r['config']} / {r['task']}: {r['failed_checks'] or r['status']}" for r in rows if r['passed'] is not True]
    atomic_write(out/'COVERAGE.md','\n'.join(lines)+'\n')


def execution_order(rows,runtime_version):
    priority=(['matched-comparison'] if runtime_version=='v2' else [])+PRIORITY
    rank={name:i for i,name in enumerate(priority)}
    return sorted((r for r in rows if r['status'] in PENDING),key=lambda r:rank.get(r['task'],len(rank)))


async def evaluate(configs=('A','B'),trials=1,limit=None,runtime_version='v1',output=None,purpose='suite',task_ids=None):
    from .app import PROJECT
    project=Path(PROJECT)
    if runtime_version not in {'v1','v2'}:raise data.Problem('runtime_version','Choose v1 or v2')
    if trials!=1:raise data.Problem('trials','One fresh trial per task is supported; use a separate run for repeated trials')
    if not configs or len(set(configs))!=len(configs) or any(c not in {'A','B'} for c in configs):raise data.Problem('configs','Choose unique reviewer configurations A and/or B')
    if limit is not None and (type(limit) is not int or not 1<=limit<=len(TASKS)):raise data.Problem('limit','Task limit must be between 1 and 18')
    if task_ids is not None:
        if limit is not None or not task_ids or len(set(task_ids))!=len(task_ids) or not set(task_ids)<={t['id'] for t in TASKS}:
            raise data.Problem('task_selection','Choose unique known task IDs without --limit')
        tasks=[t for t in TASKS if t['id'] in task_ids]
    else:tasks=TASKS[:limit] if limit else TASKS
    module={'v1':legacy_v1,'v2':agent}[runtime_version]
    store=Store(project/'runtime/evaluation');bridge=await Bridge(store.root).open()
    try:
        schemas=bridge.schemas()+module.local_schemas()
        if runtime_version=='v1':verify_v1_source(schemas)
        meta=fingerprint(runtime_version,schemas,tasks,configs,os.getenv('MODELCHECK_MODEL',module.MODEL))
        meta['purpose']=purpose if purpose!='suite' else 'targeted' if task_ids is not None else 'subset' if limit is not None else 'suite'
        if output is not None:out=Path(output).resolve()
        elif runtime_version=='v1' and list(configs)==['A','B'] and limit is None and task_ids is None:out=project/'submission'
        else:out=project/f"submission/evaluations/{runtime_version}/{meta['fingerprint'][:16]}"
        archive=(project/'submission/evaluations/v1/initial').resolve()
        if out.resolve()==archive or archive in out.resolve().parents:raise data.Problem('snapshot_protected','The original v1 snapshot is immutable',409)
        if runtime_version=='v2' and out.resolve()==(project/'submission').resolve():raise data.Problem('evaluation_directory','v2 cannot write into the v1 submission directory',409)
        with run_lock(project,out):
            state=prepare(out,meta,tasks,project);rows=state['rows']
            atomic_write(out/'tasks.jsonl',''.join(json.dumps(t)+'\n' for t in tasks))
            atomic_json(out/'metadata.json',meta)
            def persist(reason=None):
                state['stop_reason']=reason
                atomic_json(out/'progress.json',state)
                write_outputs(out,rows,meta,reason)
            persist('ready')
            pending=execution_order(rows,runtime_version)
            if not pending:persist();return 0 if all(r['passed'] is True for r in rows) else 1
            if runtime_version=='v2' and not baseline_complete(project):
                for row in pending:row['status']='pending_baseline';row['failed_checks']='v1 full-suite execution is incomplete'
                persist('v1_incomplete');print('INCOMPLETE: v1 must finish before v2 live evaluations.',flush=True);return 2
            if not os.getenv('OPENROUTER_API_KEY'):
                for row in pending:row['status']='pending_key';row['failed_checks']='API key not configured'
                persist('missing_key');return 2
            for row in pending:
                row['status']='pending_quota';row['failed_checks']='not run'
            for row in pending:
                remaining=await quota()
                if remaining is None or remaining<13:
                    persist('quota_unavailable' if remaining is None else 'quota_reserve')
                    print(f'INCOMPLETE: remaining quota {remaining}; 13 required (8 maximum plus 5 reserved).',flush=True);return 2
                task=next(t for t in tasks if t['id']==row['task'])
                owner,_=store.session();bid=store.put(owner,'bundle',fixture(task));rid=store.put(owner,'review',{'status':'queued','mode':'live','bundle_id':bid})
                result=await module.Reviewer(store,bridge).run(owner,rid,bid,task['prompt'],row['config'],allow_fallback=False)
                checks=grade(task,result,store,owner)
                trace=f"traces/{task['id']}-{row['config']}.json";usage=result.get('usage',{})
                row.update(status=result['status'],passed=all(x['passed'] for x in checks),failed_checks='; '.join(x['check'] for x in checks if not x['passed'])+((': '+result['error']['code']) if result.get('error') else ''),requests=usage.get('requests',0),input_tokens=usage.get('input_tokens',0),output_tokens=usage.get('output_tokens',0),actual_cost=usage.get('actual_cost'),seconds=result.get('seconds'),trace=trace)
                payload={'task':task,'config':row['config'],'runtime_version':runtime_version,'fingerprint':meta['fingerprint'],
                  'provenance':{'recorded_at':datetime.now(timezone.utc).isoformat(),'runner_sha256':sha(Path(__file__).read_bytes()),'requested_model':meta['model'],'served_models':result.get('served_models',[])},'run':result,'checks':checks,'row':dict(row)}
                if (out/trace).exists():raise data.Problem('trace_exists','Existing execution trace cannot be overwritten',409)
                atomic_json(out/trace,payload)
                state['trace_hashes'][trace]=sha((out/trace).read_bytes())
                persist('running')
                print(row['config'],task['id'],row['status'],'PASS' if row['passed'] else row['failed_checks'],flush=True)
            persist()
            return 0 if all(r['passed'] is True for r in rows) else 1
    finally:await bridge.close()


async def smoke(runtime_version='v2'):
    from .app import PROJECT
    directory=Path(PROJECT)/'runtime/smoke'/uuid.uuid4().hex
    return await evaluate(['B'],1,5,runtime_version,directory,'smoke')
