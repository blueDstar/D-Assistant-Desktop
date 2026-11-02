"""Explicit online preparation. Runtime model loading never downloads files."""
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import DATA


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "D-bot-model-setup"}), timeout=120)


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size:
        return
    print(f"Download {target.name}", flush=True)
    temp = target.with_suffix(target.suffix + ".part")
    with fetch(url) as source, temp.open("wb") as output:
        while data := source.read(1024 * 1024):
            output.write(data)
    temp.replace(target)


def prepare_voice():
    manifests = []
    for repo, prefix, selected, folder in [
        ("Systran/faster-whisper-base", "", {"config.json", "model.bin", "tokenizer.json", "vocabulary.json", "vocabulary.txt", "preprocessor_config.json"}, DATA / "models" / "whisper-base"),
        ("rhasspy/piper-voices", "vi/vi_VN/vais1000/medium/", {"vi_VN-vais1000-medium.onnx", "vi_VN-vais1000-medium.onnx.json", "MODEL_CARD"}, DATA / "models"),
    ]:
        with fetch(f"https://huggingface.co/api/models/{repo}") as response:
            info = json.load(response)
        revision = info["sha"]
        names = {item["rfilename"] for item in info["siblings"]}
        artifacts = []
        for name in sorted(selected):
            if prefix + name not in names:
                continue
            target = folder / ("vais1000-MODEL_CARD.md" if name == "MODEL_CARD" else name)
            download(f"https://huggingface.co/{repo}/resolve/{revision}/{prefix}{name}", target)
            artifacts.append({"path": str(target.relative_to(DATA)), "bytes": target.stat().st_size, "sha256": hashlib.file_digest(target.open("rb"), "sha256").hexdigest()})
        manifests.append({"repo": repo, "revision": revision, "artifacts": artifacts})
    (DATA / "models" / "voice-manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
    print("Voice assets prepared. Runtime uses local paths only.", flush=True)


if __name__ == "__main__":
    if "--tokenizer" in sys.argv:
        download("https://huggingface.co/Qwen/Qwen3-1.7B/resolve/main/tokenizer.json", DATA / "models" / "qwen3-tokenizer.json")
    if "--voice" in sys.argv:
        prepare_voice()
    else:
        print("Chọn rõ --voice để tải Whisper base đa ngôn ngữ (~145 MB) và Piper vi_VN (~64 MB).")
