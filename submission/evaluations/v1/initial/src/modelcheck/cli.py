import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    from dotenv import load_dotenv
    from .app import PROJECT
    load_dotenv(PROJECT/'.env')
    p=argparse.ArgumentParser(description='ModelCheck: evidence-grounded experiment review')
    sub=p.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8787)
    ask=sub.add_parser('ask');ask.add_argument('question');ask.add_argument('--sample',default='comparison');ask.add_argument('--config',choices=['A','B'],default='B')
    ev=sub.add_parser('eval');ev.add_argument('--config',nargs='+',choices=['A','B'],default=['A','B']);ev.add_argument('--trials',type=int,default=1);ev.add_argument('--limit',type=int)
    sub.add_parser('check');sub.add_parser('samples')
    a=p.parse_args()
    if a.command=='serve':
        import uvicorn
        from .app import create_app
        uvicorn.run(create_app(),host='127.0.0.1',port=a.port)
    elif a.command=='ask':
        asyncio.run(ask_once(a))
    elif a.command=='eval':
        from .evaluation import evaluate
        sys.exit(asyncio.run(evaluate(a.config,a.trials,a.limit)))
    elif a.command=='samples':
        from .samples import CATALOG
        print(json.dumps(CATALOG,indent=2))
    elif a.command=='check':
        r=subprocess.run([sys.executable,'-m','pytest',str(PROJECT/'tests'),'-q'])
        if r.returncode:sys.exit(r.returncode)
        if not os.getenv('OPENROUTER_API_KEY'):
            print('INCOMPLETE: deterministic checks passed; live smoke needs OPENROUTER_API_KEY.');sys.exit(2)
        from .evaluation import evaluate
        sys.exit(asyncio.run(evaluate(['B'],1,5)))

async def ask_once(a):
    from .app import PROJECT
    from .store import Store
    from .samples import bundle
    from .bridge import Bridge
    from .agent import Reviewer
    store=Store(PROJECT/'runtime');owner,_=store.session();bid=store.put(owner,'bundle',bundle(a.sample))
    rid=store.put(owner,'review',{'status':'queued','mode':'live','bundle_id':bid})
    b=await Bridge(store.root).open()
    try:
        result=await Reviewer(store,b).run(owner,rid,bid,a.question,a.config)
        print(json.dumps(result,indent=2))
    finally:await b.close()

if __name__=='__main__':main()
