"""Own Ollama and its runners in a Windows job; cooperative stop needs no elevation."""
import ctypes
from pathlib import Path
import os
import subprocess
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
STOP = ROOT / '.runtime' / 'stop-ollama'


class BasicLimits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', ctypes.c_uint32), ('min_working', ctypes.c_size_t), ('max_working', ctypes.c_size_t), ('active', ctypes.c_uint32), ('affinity', ctypes.c_size_t), ('priority', ctypes.c_uint32), ('scheduling', ctypes.c_uint32)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ['read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes']]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]


def create_owned_job(process):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, int(process._handle)):
        error = ctypes.get_last_error()
        if job: kernel.CloseHandle(job)
        raise OSError(error, 'Không tạo được Windows job riêng cho Ollama')
    return kernel, job


if __name__ == '__main__':
    profile = ROOT / '.runtime' / 'ollama-profile'
    profile.mkdir(exist_ok=True)
    env = os.environ | {'USERPROFILE': str(profile), 'OLLAMA_NO_CLOUD': '1', 'OLLAMA_HOST': '127.0.0.1:11434', 'OLLAMA_MODELS': str(ROOT / 'data/models/ollama'), 'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1', 'OLLAMA_MAX_QUEUE': '8', 'OLLAMA_CONTEXT_LENGTH': '4096', 'OLLAMA_VULKAN': '0'}
    process = subprocess.Popen([str(ROOT / '.runtime/ollama/ollama.exe'), 'serve'], env=env, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr, creationflags=subprocess.CREATE_NO_WINDOW)
    kernel, job = None, None
    try:
        kernel, job = create_owned_job(process)
        print(f'D-bot owns Ollama PID {process.pid} in a private kill-on-close job.', flush=True)
        while process.poll() is None:
            if STOP.exists():
                break
            time.sleep(.4)
    finally:
        if job:
            kernel.CloseHandle(job)
        elif process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
