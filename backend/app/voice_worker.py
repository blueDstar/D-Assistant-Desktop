"""Owned audio worker: reuse models between turns; release after idle/cancellation."""
import io
import json
import os
import re
import sys
import wave
import base64
import time

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["OMP_NUM_THREADS"] = "2"
from .config import STT_PATH, STT_LEARNING_PATH, TTS_PATH
from .citations import SOURCE_MARK
_STT_MODEL = None
_STT_KEY = None
_TTS_MODEL = None


def stt_model():
    return load_stt(STT_PATH)


def learning_stt_model():
    return load_stt(STT_LEARNING_PATH)


def load_stt(path):
    global _STT_MODEL, _STT_KEY
    if _STT_MODEL is None or _STT_KEY!=str(path):
        import gc
        _STT_MODEL=None;gc.collect()
        from faster_whisper import WhisperModel
        _STT_MODEL = WhisperModel(str(path), device='cpu', compute_type='int8', cpu_threads=2, num_workers=1, local_files_only=True)
        _STT_KEY=str(path)
    return _STT_MODEL


def tts_model():
    global _TTS_MODEL
    if _TTS_MODEL is None:
        from piper import PiperVoice, PiperConfig
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(str(TTS_PATH), sess_options=options, providers=['CPUExecutionProvider'])
        _TTS_MODEL = PiperVoice(session=session, config=PiperConfig.from_dict(json.loads(type(TTS_PATH)(str(TTS_PATH) + '.json').read_text(encoding='utf-8'))))
    return _TTS_MODEL


def speech_text(text, overrides=None):
    text = re.sub(r"```[\s\S]*?```", " Đoạn mã được hiển thị trong câu trả lời. ", text)
    text = re.sub(r"https?://\S+", " đường dẫn trong câu trả lời ", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = SOURCE_MARK.sub('', text)
    text = re.sub(r"(?m)^.*\|.*$", "", text)
    text = re.sub(r"[*#`_~]", "", text)
    dictionary = {"PID": "pi ai đi", "PWM": "pi vê kép em", "CAN": "can", "ESP32": "e ét pi ba mươi hai", "Python": "pai thờn", "PowerPoint":"pao pôi", "VS Code":"vi ét cốt", "D-bot":"đi bót"} | (overrides or {})
    for key, value in dictionary.items():
        text = re.sub(r"\b" + re.escape(key) + r"\b", lambda match: value, text)
    return text.strip()[:2500]


def transcribe(payload):
    import numpy as np
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    audio = decode_audio(io.BytesIO(payload["audio"]), sampling_rate=16000)
    duration = len(audio) / 16000
    if duration > 90:
        raise ValueError("Chỉ nhận tối đa 90 giây âm thanh.")
    if duration < 0.10 or not len(audio) or float(np.sqrt(np.mean(audio ** 2))) < 0.002:
        return {"text": "", "silence": True, "duration_seconds": duration, "segments": []}
    learning=payload.get('language') in {'en','ja'} or payload.get('context','general')=='general'
    path=STT_LEARNING_PATH if learning and (STT_LEARNING_PATH/'model.bin').exists() else STT_PATH
    missing = [name for name in ['model.bin', 'config.json', 'tokenizer.json'] if not (path / name).exists()]
    if not any((path / name).exists() for name in ['vocabulary.txt', 'vocabulary.json']):
        missing.append('vocabulary.txt (hoặc vocabulary.json)')
    if missing:
        raise ValueError(f"Thiếu Whisper {', '.join(missing)} tại {path}. Chạy prepare_models.ps1 -Voice. Runtime không tự tải.")
    model = learning_stt_model() if path!=STT_PATH else stt_model()
    hint=None
    if payload['language']=='vi' and payload.get('context')=='desktop':hint='Hội thoại tiếng Việt về ứng dụng: mở PowerPoint, Word, Excel, Outlook, VS Code, Chrome, Notepad. Có. Không.'
    elif payload['language']=='vi' and payload.get('context')=='confirmation':hint='Câu trả lời tiếng Việt: Có. Không. Vâng. Đồng ý. Hủy. Mở PowerPoint. Mở Word. Mở Excel.'
    language=payload.get('language','auto')
    if language not in {'auto','vi','en','ja'}:raise ValueError('Ngôn ngữ nhận dạng không hợp lệ')
    segments, info = model.transcribe(audio, language=None if language == 'auto' else language, beam_size=5, vad_filter=True, condition_on_previous_text=False, initial_prompt=hint, vad_parameters={"min_silence_duration_ms": 400})
    result = [{"start": s.start, "end": s.end, "text": s.text} for s in segments if s.no_speech_prob < 0.8]
    text = " ".join(s["text"].strip() for s in result).strip()
    return {"text": text, "silence": not bool(text), "duration_seconds": duration, "language": info.language, "segments": result, 'model':path.name}


def synthesize(payload):
    if payload.get('language','vi') in {'en','ja'}:
        from .language_tts import synthesize as language_speech
        return language_speech(payload['text'],payload['language'],payload.get('speed',1.0))
    from piper import PiperVoice, SynthesisConfig
    if not TTS_PATH.exists() or not type(TTS_PATH)(str(TTS_PATH) + ".json").exists():
        raise ValueError("Thiếu voice vi_VN-vais1000-medium.onnx hoặc .onnx.json. Chạy prepare_models.ps1 -Voice.")
    text = speech_text(payload["text"], payload.get('pronunciations'))
    if not text:
        raise ValueError("Không có văn bản phù hợp để đọc.")
    voice = tts_model()
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        voice.synthesize_wav(text, audio, syn_config=SynthesisConfig(length_scale=voice.config.length_scale))
    from .audio_tempo import speech_tempo
    return speech_tempo(output.getvalue(),payload['speed'])


def serve():
    for line in sys.stdin.buffer:
        started = time.perf_counter()
        try:
            request = json.loads(line)
            mode, payload = request['mode'], request.get('payload', {})
            if mode == 'stt':
                payload['audio'] = base64.b64decode(payload['audio'], validate=True)
                result = transcribe(payload)
            elif mode == 'tts':
                result = {'audio': base64.b64encode(synthesize(payload)).decode('ascii')}
            elif mode == 'warm':
                stt_model(); tts_model()
                result = {'ready': True}
            else:
                raise ValueError('Voice worker mode không hợp lệ')
            loaded=[name for name, model in [('stt', _STT_MODEL), ('tts', _TTS_MODEL)] if model is not None]
            language_module=sys.modules.get('app.language_tts')
            if language_module and language_module._MODEL is not None:loaded.append('tts_en_ja')
            if _STT_MODEL is not None and _STT_KEY==str(STT_LEARNING_PATH):loaded.append('stt_learning')
            response = {'id': request['id'], 'ok': True, 'result': result, 'worker_seconds': time.perf_counter() - started, 'loaded':loaded}
        except Exception as error:
            response = {'id': request.get('id') if 'request' in locals() else None, 'ok': False, 'error': f'{type(error).__name__}: {error}'}
        sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode('utf-8') + b'\n')
        sys.stdout.buffer.flush()


if __name__ == "__main__" and sys.argv[1] == 'serve':
    serve()
elif __name__ == '__main__':
    try:
        mode = sys.argv[1]
        raw = sys.stdin.buffer.read(16 * 1024 * 1024)
        if mode == "stt":
            language, audio = raw.split(b"\n", 1)
            output = json.dumps(transcribe({"audio": audio, "language": language.decode()}), ensure_ascii=False).encode("utf-8")
        elif mode == "tts":
            output = synthesize(json.loads(raw))
        else:
            raise ValueError("Worker mode không hợp lệ")
        sys.stdout.buffer.write(output)
    except Exception as error:
        sys.stderr.write(f"{type(error).__name__}: {error}")
        sys.exit(1)
