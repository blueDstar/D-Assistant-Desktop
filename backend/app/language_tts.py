"""English/Japanese CPU ONNX TTS; separate from Piper Vietnamese, strictly local."""
import io
import wave

from .config import DATA
from .audio_tempo import speech_tempo

_MODEL=None
_JA=None


def synthesize(text,language,speed):
    global _MODEL,_JA
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro
    directory=DATA/'models/kokoro'
    # FP32 was 6–9x faster than the dynamic INT8 export on this CPU.
    model=directory/'kokoro-v1.0.onnx';voices=directory/'voices-v1.0.bin'
    if not model.exists() or not voices.exists():
        raise ValueError('Chưa tải giọng Anh–Nhật. Chạy scripts/prepare_language_tts.py khi có mạng.')
    if _MODEL is None:
        options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
        options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        session=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider'])
        _MODEL=Kokoro.from_session(session,str(voices))
    if language=='ja':
        if _JA is None:
            from misaki import ja
            _JA=ja.JAG2P()
        phonemes,_=_JA(text[:2500])
        samples,rate=_MODEL.create(phonemes,voice='jf_alpha',speed=1.0,is_phonemes=True)
    elif language=='en':
        samples,rate=_MODEL.create(text[:2500],voice='af_heart',speed=1.0,lang='en-us')
    else:
        raise ValueError('Giọng học chỉ hỗ trợ en/ja')
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())
    return speech_tempo(output.getvalue(),speed)
