import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
os.environ['OTEL_SDK_DISABLED'] = 'true'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
DATA = Path(os.getenv("DBOT_DATA_DIR", str(ROOT / "data"))).resolve()
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
parsed = urlparse(OLLAMA_URL)
if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.path not in {"", "/"}:
    raise ValueError("Ollama phải dùng HTTP loopback, không có tài khoản/path.")
PORT = int(os.getenv("DBOT_PORT", "8008"))
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}", "http://127.0.0.1:5173", "http://localhost:5173"}
DEFAULTS = {
    "model": os.getenv("OLLAMA_MODEL", "dbot-qwen35:4b"),
    "context": int(os.getenv("OLLAMA_CONTEXT", "4096")),
    "max_output": 1536,
    "temperature": 0.3,
    "offline": os.getenv("OFFLINE_MODE", "1") == "1",
    "save_history": os.getenv("SAVE_HISTORY", "1") == "1",
    "user_name": "Bạn",
    "address_style": "Gọi người dùng bằng tên, xưng mình.",
    "allowed_roots": [],
    "tts_speed": 1.0,
    "stt_language": "vi",
    "native_tools": True,
    "auto_speak": False,
    "pronunciations": {"PID": "pi ai đi", "PWM": "pi vê kép em", "CAN": "can", "ESP32": "e ét pi ba mươi hai", "Python": "pai thờn"},
    'fast_model': 'dbot-qwen35:4b',
    'performance': 'auto',
    'keep_alive': '5m',
    'coding_model': 'dbot-qwen35:4b',
    'learn_from_conversations': False,
}
TIMEOUT = int(os.getenv("MODEL_TIMEOUT", "600"))
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_MB", "12")) * 1024 * 1024
STT_PATH = Path(os.getenv("STT_MODEL_PATH", str(DATA / "models" / "whisper-base"))).resolve()
STT_LEARNING_PATH = Path(os.getenv('STT_LEARNING_MODEL_PATH', str(DATA / 'models' / 'whisper-small'))).resolve()
TTS_PATH = Path(os.getenv("TTS_VOICE_PATH", str(DATA / "models" / "vi_VN-vais1000-medium.onnx"))).resolve()
for directory in (DATA, DATA / "database", DATA / "knowledge", DATA / "exports", DATA / "backups", DATA / "models", DATA / 'audio_temp'):
    directory.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(DATA / 'audio_temp')
