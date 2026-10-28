"""A real MCP connection, kept on the application's async event loop."""
import json
import os
import sys
from contextlib import AsyncExitStack
from mcp import Client,StdioServerParameters
from .data import Problem

class Bridge:
    def __init__(self,root):self.root=str(root);self.stack=AsyncExitStack();self.client=None;self.catalog=[]
    async def open(self):
        params=StdioServerParameters(command=sys.executable,args=["-m","modelcheck.mcp_server"],env={**os.environ,"MODELCHECK_RUNTIME":self.root})
        self.client=await self.stack.enter_async_context(Client(params))
        self.catalog=(await self.client.list_tools()).tools
        return self
    async def close(self):await self.stack.aclose()
    def schemas(self):
        schemas=[]
        for t in self.catalog:
            p=json.loads(json.dumps(t.input_schema))
            p["properties"].pop("owner",None)
            p["required"]=[k for k in p.get("required",[]) if k!="owner"]
            p["additionalProperties"]=False
            schemas.append({"type":"function","function":{"name":t.name,"description":t.description,"parameters":p}})
        return schemas
    async def call(self,name,args,owner,bundle_id):
        if name not in {t.name for t in self.catalog} or "owner" in args:
            raise Problem("tool_denied","Unknown tool or attempted owner override")
        if args.get("bundle_id") != bundle_id:
            raise Problem("foreign_bundle","Tool may inspect only the current bundle")
        result=await self.client.call_tool(name,{**args,"owner":owner})
        text="\n".join(c.text for c in result.content if hasattr(c,"text"))
        if result.is_error:raise Problem("tool_error",text)
        try:return json.loads(text)
        except ValueError:return {"text":text}
