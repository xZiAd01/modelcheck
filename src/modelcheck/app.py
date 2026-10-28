"""Local same-origin UI/API. Never exposes an API credential to the page."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends,FastAPI,Header,Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Reviewer
from .bridge import Bridge
from .data import Problem,build_bundle,inspect
from .store import Store
from . import samples

PACKAGE=Path(__file__).parent
PROJECT=PACKAGE.parents[1]

class BundleIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    sample_id:str|None=None
    manifest_csv:str=""
    predictions:list[str]=Field(default_factory=list)
    metadata:dict=Field(default_factory=dict)

class ReviewIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    bundle_id:str=Field(max_length=100)
    question:str=Field(min_length=1,max_length=4000)
    config:str=Field(default="B",pattern="^[AB]$")

class DecisionIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    approved:bool
    digest:str=Field(min_length=64,max_length=64)

class ProposalIn(BaseModel):
    model_config=ConfigDict(extra="forbid")
    review_id:str
    spec:dict

def create_app(root=None):
    load_dotenv(PROJECT/".env")
    store=Store(root or os.getenv("MODELCHECK_RUNTIME",PROJECT/"runtime"))
    bridge=Bridge(store.root)
    queue=asyncio.Queue(maxsize=3)

    async def worker():
        while True:
            owner,rid,req=await queue.get()
            try:
                await Reviewer(store,bridge).run(owner,rid,req.bundle_id,req.question,req.config)
            except Problem:pass
            finally:queue.task_done()

    @asynccontextmanager
    async def lifespan(app):
        await bridge.open()
        task=asyncio.create_task(worker())
        try:yield
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
            await bridge.close()

    app=FastAPI(title="ModelCheck",version="0.1.0",lifespan=lifespan)
    app.state.store=store;app.state.bridge=bridge
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost","testserver"])

    @app.middleware("http")
    async def boundaries(request,call_next):
        from urllib.parse import urlsplit
        origin=request.headers.get("origin")
        parsed=urlsplit(origin) if origin else None
        same_origin=bool(parsed and parsed.scheme=="http" and parsed.hostname in {"127.0.0.1","localhost","testserver"} and parsed.netloc==request.headers.get("host"))
        if origin and not same_origin:
            return JSONResponse({"error":{"code":"origin_denied","message":"Use the local ModelCheck page"}},status_code=403)
        if request.method in {"POST","DELETE"} and request.headers.get("content-type","").split(";")[0]!="application/json":
            return JSONResponse({"error":{"code":"json_required","message":"JSON request required"}},status_code=415)
        if request.method=="POST":
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>4*1024*1024:return JSONResponse({"error":{"code":"body_too_large","message":"Request limit is 4 MiB"}},status_code=413)
                chunks.append(chunk)
            request._body=b"".join(chunks)
        response=await call_next(request)
        response.headers["X-Content-Type-Options"]="nosniff"
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["Cache-Control"]="no-store"
        return response

    @app.exception_handler(Problem)
    async def problem_handler(request,exc):
        return JSONResponse({"error":{"code":exc.code,"message":str(exc)}},status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request,exc):
        details=[{"field":".".join(map(str,e["loc"])),"message":e["msg"]} for e in exc.errors()]
        return JSONResponse({"error":{"code":"validation","message":"Check the supplied fields","details":details}},status_code=422)

    def owner(authorization:str=Header(default="")):
        return store.owner(authorization.removeprefix("Bearer "))

    @app.get("/healthz")
    async def health():
        # Re-read a newly entered local key without restarting the app.
        load_dotenv(PROJECT/".env",override=True)
        return {"ok":True,"mcp_ready":bridge.client is not None,"api_key_configured":bool(os.getenv("OPENROUTER_API_KEY")),
                "model":os.getenv("MODELCHECK_MODEL","nvidia/nemotron-3.5-lightning:free"),"mode":"local","version":"0.1.0"}

    @app.post("/api/sessions")
    async def session():
        _,token=store.session();return {"token":token}

    @app.delete("/api/sessions/current")
    async def reset(who=Depends(owner)):
        store.reset(who);return {"reset":True}

    @app.get("/api/samples")
    async def catalog():return samples.CATALOG

    @app.get("/api/samples/{sid}/files")
    async def sample_files(sid:str):
        if sid not in {s["id"] for s in samples.CATALOG}:raise Problem("not_found","Sample not found",404)
        return samples.files(sid)

    @app.post("/api/bundles")
    async def import_bundle(req:BundleIn,who=Depends(owner)):
        if req.sample_id:
            if req.sample_id not in {s["id"] for s in samples.CATALOG}:raise Problem("not_found","Sample not found",404)
            data=samples.bundle(req.sample_id)
        else:data=build_bundle(req.manifest_csv,req.predictions,req.metadata)
        bid=store.put(who,"bundle",data)
        return {"bundle_id":bid,"validation":inspect(data)}

    @app.post("/api/inspections")
    async def inspection(req:ReviewIn,who=Depends(owner)):
        data=store.get(who,"bundle",req.bundle_id)
        rid=store.put(who,"review",{"status":"running","mode":"deterministic","events":[],"evidence":[]})
        evidence=[];events=[]
        calls=[("inspect_manifest",{})]+[("compute_metrics",{"run_id":r["id"]}) for r in data["runs"]]
        if len(data["runs"])==2:calls.append(("compare_runs",{}))
        for name,args in calls:
            try:
                result=await bridge.call(name,{"bundle_id":req.bundle_id,**args},who,req.bundle_id)
                e=store.evidence(who,rid,name,result);evidence.append(e)
                events.append({"kind":"tool_result","tool":name,"evidence_id":e["evidence_id"]})
            except Problem as exc:events.append({"kind":"tool_blocked","tool":name,"error":{"code":exc.code,"message":str(exc)}})
        result={"status":"completed","mode":"deterministic","bundle_id":req.bundle_id,"events":events,"evidence":evidence,
                "report":{"summary":"Deterministic data inspection complete. These are tool calculations, not an LLM review.",
                    "findings":[{"statement":f["message"],"severity":f["severity"],"issue_codes":[f["code"]],"evidence_ids":[evidence[0]["evidence_id"]]} for f in inspect(data)["findings"]],
                    "limitations":["Synthetic examples demonstrate functionality, not historical model performance.","Local interface; live model inference, when used, is sent to OpenRouter."]}}
        store.put(who,"review",result,rid)
        return {"id":rid,**result}

    @app.post("/api/reviews",status_code=202)
    async def review(req:ReviewIn,who=Depends(owner)):
        load_dotenv(PROJECT/".env",override=True)
        if not os.getenv("OPENROUTER_API_KEY"):raise Problem("missing_api_key","Add the key to modelcheck/.env. Data inspection works without it.",503)
        store.get(who,"bundle",req.bundle_id)
        if queue.full():raise Problem("queue_full","Review queue is full. Wait for the current review.",429)
        rid=store.put(who,"review",{"status":"queued","mode":"live","bundle_id":req.bundle_id,"config":req.config,"question":req.question,"events":[],"evidence":[]})
        queue.put_nowait((who,rid,req))
        return {"id":rid,"status":"queued"}

    @app.get("/api/reviews/{rid}")
    async def get_review(rid:str,who=Depends(owner)):
        result=store.get(who,"review",rid)
        if result.get("pending_action"):
            aid=result["pending_action"]["id"]
            result["pending_action"]={"id":aid,**store.get(who,"action",aid)}
        return {"id":rid,**result}

    @app.post("/api/proposals")
    async def manual_proposal(req:ProposalIn,who=Depends(owner)):
        result=store.get(who,"review",req.review_id)
        if result.get("status")!="completed":raise Problem("review_incomplete","Complete the review before drafting a proposal",409)
        action=store.propose(who,req.review_id,result["bundle_id"],req.spec)
        result["pending_action"]=action;store.put(who,"review",result,req.review_id)
        return action

    @app.post("/api/replays/comparison")
    async def replay(who=Depends(owner)):
        import copy
        source=PACKAGE/"recorded/comparison.json"
        if not source.exists():raise Problem("replay_unavailable","No successful recorded run is available",404)
        original=json.loads(source.read_text())
        bid=store.put(who,"bundle",samples.bundle("comparison"))
        rid=store.put(who,"review",{"status":"running","mode":"recorded","bundle_id":bid})
        result=copy.deepcopy(original)
        result.update(mode="recorded",bundle_id=bid,pending_action=None)
        mapping={};evidence=[]
        for e in original.get("evidence",[]):
            saved=store.evidence(who,rid,e["tool"],e["result"])
            mapping[e["evidence_id"]]=saved["evidence_id"];evidence.append(saved)
        result["evidence"]=evidence
        for finding in result.get("report",{}).get("findings",[]):
            finding["evidence_ids"]=[mapping[e] for e in finding["evidence_ids"]]
        for event in result.get("events",[]):
            if event.get("evidence_id") in mapping:event["evidence_id"]=mapping[event["evidence_id"]]
        result["report"]["summary"]="Recorded AI review (28 October 2026, synthetic data). No model request runs during replay. "+result["report"]["summary"]
        result["application_notice"]="Evidence check: the recorded model says the test set was not used for tuning. Prediction exports cannot establish that claim. Treat training and preprocessing metadata as unverified declarations."
        result["validation"]=inspect(samples.bundle("comparison"))
        store.put(who,"review",result,rid)
        return {"id":rid,**result}

    @app.post("/api/actions/{aid}/decision")
    async def decision(aid:str,req:DecisionIn,who=Depends(owner)):
        action=store.decide(who,aid,req.approved,req.digest)
        review=store.get(who,"review",action["review_id"])
        review["pending_action"]=action
        store.put(who,"review",review,action["review_id"])
        return action

    @app.get("/api/actions/{aid}/download")
    async def action_file(aid:str,who=Depends(owner)):
        action=store.get(who,"action",aid)
        if action["status"]!="saved":raise Problem("not_saved","Approve the specification first",409)
        return Response(json.dumps(action["spec"],indent=2),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="{aid}.json"'})

    @app.get("/api/reviews/{rid}/export")
    async def export(rid:str,format:str="json",who=Depends(owner)):
        result=store.get(who,"review",rid)
        if format not in {"json","markdown"}:raise Problem("bad_format","Choose json or markdown")
        text=json.dumps(result,indent=2,ensure_ascii=False)
        if format=="markdown":
            report=result.get("report",{})
            text="# ModelCheck review\n\nMode: "+result.get("mode","live")+"\n\n"+report.get("summary","")+"\n\n"+"\n".join("- "+f["statement"]+" ["+", ".join(f["evidence_ids"])+"]" for f in report.get("findings",[]))+"\n\n## Evidence\n\n```json\n"+json.dumps(result.get("evidence",[]),indent=2)+"\n```\n"
            if result.get("application_notice"):
                text+="\n## Evidence qualification\n\n"+result["application_notice"]+"\n"
        return Response(text,media_type="text/plain" if format=="markdown" else "application/json",headers={"Content-Disposition":f'attachment; filename="{rid}.{"md" if format=="markdown" else "json"}"'})

    app.mount("/static",StaticFiles(directory=PACKAGE/"static"),name="static")
    @app.get("/")
    async def index():return FileResponse(PACKAGE/"static/index.html")
    return app
