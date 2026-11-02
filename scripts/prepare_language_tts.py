"""Download small CPU TTS, pinned upstream release + SHA256; no runtime downloads."""
import hashlib,json
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'data/models/kokoro';folder.mkdir(parents=True,exist_ok=True)
assets={'kokoro-v1.0.onnx':'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a','voices-v1.0.bin':'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d'}
import sys
if '--int8' in sys.argv:assets['kokoro-v1.0.int8.onnx']='ae315a79b623f244700e4afb9246c46a26066782e049ba174bf3ba433970ee9c'
records=[]
with httpx.Client(trust_env=False,timeout=120,follow_redirects=True) as client:
    for name,digest in assets.items():
        target=folder/name
        def sha(p):
            with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
        url='https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/'+name
        if not target.exists() or sha(target)!=digest:
            part=target.with_suffix('.part')
            with client.stream('GET',url) as response,part.open('wb') as output:
                response.raise_for_status()
                for block in response.iter_bytes(1024*1024):output.write(block)
            if sha(part)!=digest:raise ValueError('Hash mismatch: '+name)
            part.replace(target)
        records.append({'path':name,'sha256':digest,'bytes':target.stat().st_size,'url':url})
        print('Verified '+name,flush=True)
(folder/'manifest.json').write_text(json.dumps({'license':'Apache-2.0 weights; MIT kokoro-onnx','upstream':'https://huggingface.co/hexgrad/Kokoro-82M','artifacts':records},indent=2),encoding='utf-8')
