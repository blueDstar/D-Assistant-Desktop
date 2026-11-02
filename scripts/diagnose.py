import ctypes
import json
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
class Memory(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ['total', 'free', 'page', 'pagefree', 'virtual', 'virtualfree', 'ext']]

result = {'os': platform.platform(), 'python': sys.version, 'disk': dict(zip(['total', 'used', 'free'], shutil.disk_usage(ROOT))), 'sqlite': sqlite3.sqlite_version, 'versions': json.loads((ROOT / '.runtime' / 'versions.json').read_text())}
memory = Memory(); memory.length = ctypes.sizeof(memory)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
result['ram_bytes'] = {'total': memory.total, 'available': memory.free}
try:
    result['gpu'] = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,memory.free', '--format=csv'], text=True).strip()
except (OSError, subprocess.CalledProcessError):
    result['gpu'] = 'Không có nvidia-smi; không suy ra GPU từ đây'
for name, url in [('backend', 'http://127.0.0.1:8008/api/health'), ('ollama', 'http://127.0.0.1:11434/api/ps')]:
    try:
        result[name] = json.load(urllib.request.urlopen(url, timeout=5))
    except Exception as error:
        result[name] = type(error).__name__
print(json.dumps(result, ensure_ascii=False, indent=2))
if '--save' in sys.argv:
    (ROOT / 'docs/ENVIRONMENT_SNAPSHOT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
