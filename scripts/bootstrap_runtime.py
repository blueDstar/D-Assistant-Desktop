"""Prepare portable, official runtimes in this checkout only. No global install."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
RUNTIME.mkdir(exist_ok=True)


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "D-bot-setup"}), timeout=60) as response:
        return json.load(response)


def download(url, target, digest=None):
    def checksum(path):
        value = hashlib.sha256()
        with path.open('rb') as source:
            while block := source.read(1024 * 1024):
                value.update(block)
        return value.hexdigest()
    if target.exists() and (not digest or checksum(target) == digest):
        return
    temporary = target.with_suffix(target.suffix + ".part")
    print(f"Download {target.name}: {url}", flush=True)
    with urllib.request.urlopen(url, timeout=90) as response, temporary.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    if digest and checksum(temporary) != digest:
        raise RuntimeError(f"SHA256 mismatch: {target.name}")
    temporary.replace(target)


def prepare_node():
    versions = get_json("https://nodejs.org/dist/index.json")
    version = next(v["version"] for v in versions if v["lts"] and "win-x64-zip" in v["files"])
    name = f"node-{version}-win-x64.zip"
    base = f"https://nodejs.org/dist/{version}"
    hashes = urllib.request.urlopen(base + "/SHASUMS256.txt", timeout=60).read().decode()
    digest = next(line.split()[0] for line in hashes.splitlines() if line.endswith(" " + name))
    archive = RUNTIME / name
    download(base + "/" + name, archive, digest)
    destination = RUNTIME / "node"
    if not (destination / "node.exe").exists():
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                relative = Path(*Path(info.filename).parts[1:])
                if info.is_dir() or not relative.parts:
                    continue
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(info))
    return {"node": version, "sha256": digest}


def prepare_github(repo, asset_name, destination, cpu_only=False):
    release = get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    asset = next(a for a in release["assets"] if a["name"] == asset_name)
    archive = RUNTIME / asset_name
    digest = asset.get("digest", "").removeprefix("sha256:") or None
    download(asset["browser_download_url"], archive, digest)
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            # This machine has only 2 GB VRAM: omit heavyweight GPU libraries.
            if info.is_dir() or (cpu_only and any(s in info.filename.lower() for s in ("cuda", "rocm", "vulkan"))):
                continue
            relative = Path(info.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("Unsafe archive path")
            target = RUNTIME / destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or target.stat().st_size != info.file_size:
                target.write_bytes(bundle.read(info))
    return {repo: release["tag_name"], "asset": asset_name, "sha256": digest, "cpu_only": cpu_only}


if __name__ == "__main__":
    # Keep Python 3.9 compatibility in bootstrap; application uses managed 3.12.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        tasks = [executor.submit(prepare_node),
                 executor.submit(prepare_github, "astral-sh/uv", "uv-x86_64-pc-windows-msvc.zip", "uv"),
                 executor.submit(prepare_github, "ollama/ollama", "ollama-windows-amd64.zip", "ollama", True)]
        results = [task.result() for task in tasks]
    (RUNTIME / "versions.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2), flush=True)
