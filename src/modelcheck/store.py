"""Session-scoped persistence and the independently enforced write boundary."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from pydantic import BaseModel, ConfigDict, Field
from .data import Problem, digest


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(min_length=5,max_length=500)
    change: str = Field(min_length=5,max_length=1000)
    selection_rule: str = Field(min_length=5,max_length=500)
    success_criterion: str = Field(min_length=5,max_length=500)
    run_ids: list[str] = Field(min_length=1,max_length=2)
    evidence_ids: list[str] = Field(min_length=1,max_length=12)
    held_out_test: str = "Keep test data untouched until the final assessment. Select changes on validation data."


class Store:
    def __init__(self, root: str | Path):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/"state.sqlite"
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE, created REAL);
            CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY, owner TEXT, kind TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, owner TEXT, event TEXT, data TEXT, created REAL);
            """)

    def connect(self):
        return sqlite3.connect(self.db,timeout=20)

    def session(self) -> tuple[str,str]:
        owner="s_"+secrets.token_hex(16); token=secrets.token_urlsafe(32)
        with self.connect() as con:
            con.execute("INSERT INTO sessions VALUES(?,?,?)",(owner,hashlib.sha256(token.encode()).hexdigest(),time.time()))
        return owner,token

    def owner(self, token: str) -> str:
        with self.connect() as con:
            row=con.execute("SELECT id FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row: raise Problem("unauthorized","Create a session first",401)
        return row[0]

    def active(self, owner: str):
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM sessions WHERE id=?",(owner,)).fetchone():
                raise Problem("session_reset","Session was reset",410)

    def put(self, owner: str, kind: str, data: dict, ident: str | None = None) -> str:
        self.active(owner)
        ident=ident or kind[0]+"_"+secrets.token_hex(12)
        with self.connect() as con:
            con.execute("INSERT INTO objects VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data WHERE objects.owner=excluded.owner AND objects.kind=excluded.kind",
                        (ident,owner,kind,json.dumps(data,ensure_ascii=False,allow_nan=False)))
        return ident

    def get(self, owner: str, kind: str, ident: str) -> dict:
        self.active(owner)
        with self.connect() as con:
            row=con.execute("SELECT data FROM objects WHERE id=? AND owner=? AND kind=?",(ident,owner,kind)).fetchone()
        if not row: raise Problem("not_found",f"{kind} not found in this session",404)
        return json.loads(row[0])

    def list(self, owner: str, kind: str) -> list[dict]:
        self.active(owner)
        with self.connect() as con:
            rows=con.execute("SELECT id,data FROM objects WHERE owner=? AND kind=?",(owner,kind)).fetchall()
        return [{"id":r[0],**json.loads(r[1])} for r in rows]

    def audit(self,owner,event,data):
        with self.connect() as con:
            con.execute("INSERT INTO audit(owner,event,data,created) VALUES(?,?,?,?)",(owner,event,json.dumps(data),time.time()))

    def evidence(self,owner,review_id,tool,result):
        eid=self.put(owner,"evidence",{"review_id":review_id,"tool":tool,"result":result})
        return {"evidence_id":eid,"tool":tool,"result":result}

    def propose(self,owner,review_id,bundle_id,spec:dict):
        spec=ExperimentSpec.model_validate(spec).model_dump()
        bundle=self.get(owner,"bundle",bundle_id)
        if not set(spec["run_ids"]) <= {r["id"] for r in bundle["runs"]}:
            raise Problem("unknown_run","Proposal must use this bundle's run IDs")
        for eid in spec["evidence_ids"]:
            if self.get(owner,"evidence",eid)["review_id"] != review_id:
                raise Problem("foreign_evidence","Proposal evidence must belong to this review")
        if "validation" not in spec["selection_rule"].lower():
            raise Problem("selection_rule","Select the change on validation data, not test data")
        spec["held_out_test"]=ExperimentSpec.model_fields["held_out_test"].default
        canonical={"review_id":review_id,"bundle_id":bundle_id,"spec":spec}
        for old in self.list(owner,"action"):
            if old["digest"]==digest(canonical) and old["status"]=="pending":
                return old
        aid=self.put(owner,"action",{**canonical,"digest":digest(canonical),"status":"pending","expires":time.time()+3600})
        self.audit(owner,"proposal_created",{"action_id":aid,"review_id":review_id})
        return {"id":aid,**self.get(owner,"action",aid)}

    def decide(self,owner,aid,approved:bool,expected_digest:str):
        self.active(owner)
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT data FROM objects WHERE id=? AND owner=? AND kind='action'",(aid,owner)).fetchone()
            if not row: raise Problem("not_found","Action not found",404)
            action=json.loads(row[0])
            if not secrets.compare_digest(action["digest"],expected_digest):
                raise Problem("proposal_changed","Approval digest does not match the exact proposal",409)
            if action["status"]=="saved" and approved: return {"id":aid,**action}
            if action["status"]!="pending": raise Problem("action_closed","This action is already closed",409)
            if action["expires"]<time.time(): raise Problem("action_expired","Proposal expired; create a new one",409)
            if approved:
                if not re.fullmatch(r"[a-z]_[a-f0-9]{24}",aid): raise Problem("invalid_path","Invalid action identifier")
                directory=(self.root/"experiments"/owner).resolve()
                directory.relative_to(self.root)
                directory.mkdir(parents=True,exist_ok=True)
                target=directory/f"{aid}.json"
                temp=directory/f".{aid}.tmp"
                temp.write_text(json.dumps(action["spec"],indent=2)+"\n",encoding="utf-8")
                os.replace(temp,target)
                action.update(status="saved",filename=target.name)
            else: action["status"]="rejected"
            con.execute("UPDATE objects SET data=? WHERE id=?",(json.dumps(action),aid))
            con.execute("INSERT INTO audit(owner,event,data,created) VALUES(?,?,?,?)",(owner,"action_"+action["status"],json.dumps({"action_id":aid}),time.time()))
        return {"id":aid,**action}

    def reset(self,owner):
        import shutil
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM objects WHERE owner=?",(owner,))
            con.execute("DELETE FROM audit WHERE owner=?",(owner,))
            con.execute("DELETE FROM sessions WHERE id=?",(owner,))
        path=(self.root/"experiments"/owner).resolve()
        path.relative_to(self.root)
        if path.exists(): shutil.rmtree(path)

