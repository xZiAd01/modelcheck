"""Package portable source and synthetic evidence, excluding local state and credentials."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT.parent/'output'
EXCLUDED={'.git','.env','.venv','runtime','.build','__pycache__','.pytest_cache','node_modules','.DS_Store'}

def allowed(p):
    rel=p.relative_to(ROOT)
    return not any(x in EXCLUDED for x in rel.parts) and not p.name.endswith(('.zip','.pyc'))

def main():
    OUTPUT.mkdir(exist_ok=True)
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and allowed(p))
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (OUTPUT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    target=OUTPUT/'ModelCheck_submission.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:z.write(p,'modelcheck/'+str(p.relative_to(ROOT)))
    with zipfile.ZipFile(target) as z:
        assert not any('/.env' in name and not name.endswith('.env.example') for name in z.namelist())
        assert not any('/runtime/' in name or '/.venv/' in name or '/.build/' in name for name in z.namelist())
    print('Created',target,'with',len(files),'source/evidence files; secrets and runtime excluded.')

if __name__=='__main__':main()
