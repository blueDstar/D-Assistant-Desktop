"""Explicit HF download, pinned revisions, verified weights; never trains or uploads chats."""
import hashlib
import json
from pathlib import Path
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'data' / 'models'
ASSETS = [
    ('unsloth/Qwen3.5-4B-GGUF', 'e87f176479d0855a907a41277aca2f8ee7a09523', 'Qwen3.5-4B-Q4_K_M.gguf', 'qwen35-4b/Qwen3.5-4B-Q4_K_M.gguf'),
    ('Qwen/Qwen3.5-4B', '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a', 'tokenizer.json', 'qwen35-tokenizer.json'),
    *[('Systran/faster-whisper-small', '536b0662742c02347bc0e980a01041f333bce120', name, 'whisper-small/' + name) for name in ['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt']],
]


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def prepare(manifest_name='upgrade-v6-manifest.json'):
    manifest = []
    with httpx.Client(trust_env=False, follow_redirects=True, timeout=120) as client:
        metadata = {}
        for repo, revision, name, local in ASSETS:
            if (repo, revision) not in metadata:
                response = client.get(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true')
                response.raise_for_status()
                metadata[repo, revision] = response.json()
            info = next(row for row in metadata[repo, revision]['siblings'] if row['rfilename'] == name)
            target = TARGET / local
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = info.get('lfs', {}).get('sha256')
            size = info['size']
            if not target.exists() or target.stat().st_size != size or expected and sha(target) != expected:
                partial = target.with_suffix(target.suffix + '.part')
                offset = partial.stat().st_size if partial.exists() else 0
                if offset > size:
                    partial.unlink(); offset = 0
                print(f'Download {local}: {offset}/{size}', flush=True)
                headers = {'Range': f'bytes={offset}-'} if offset else {}
                with client.stream('GET', f'https://huggingface.co/{repo}/resolve/{revision}/{name}', headers=headers) as response:
                    response.raise_for_status()
                    if offset and response.status_code != 206:
                        offset = 0
                    if response.status_code == 206 and not response.headers.get('content-range', '').startswith(f'bytes {offset}-'):
                        raise ValueError('Unexpected download range')
                    last = time.monotonic()
                    with partial.open('ab' if offset else 'wb') as output:
                        for block in response.iter_bytes(1024 * 1024):
                            output.write(block); offset += len(block)
                            if time.monotonic() - last > 15:
                                print(f'{local}: {offset / size:.0%}', flush=True); last = time.monotonic()
                if partial.stat().st_size != size or expected and sha(partial) != expected:
                    raise ValueError('Weight size/hash mismatch: ' + local)
                partial.replace(target)
            digest = sha(target)
            # Git blobs provide integrity for small non-LFS configuration files.
            if not expected:
                raw = target.read_bytes()
                git_hash = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
                if git_hash != info['blobId']:
                    raise ValueError('Configuration git hash mismatch: ' + local)
            manifest.append({'repo': repo, 'revision': revision, 'filename': name, 'path': local, 'bytes': size, 'sha256': digest})
            print('Verified ' + local, flush=True)
    (TARGET / manifest_name).write_text(json.dumps({'weight_training_performed': False, 'assets': manifest}, indent=2), encoding='utf-8')
    print('Verified assets ready; activate only after inference checks.', flush=True)


if __name__ == '__main__':
    prepare()
