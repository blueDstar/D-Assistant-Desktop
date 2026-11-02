import io,wave
import numpy as np
import pytest
from app.audio_tempo import speech_tempo

def test_tempo_slows_speech_without_lowering_pitch():
    rate=22050;raw=(np.sin(2*np.pi*440*np.arange(rate*2)/rate)*16000).astype(np.int16);buf=io.BytesIO()
    with wave.open(buf,'wb') as out:out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(raw.tobytes())
    original=buf.getvalue();assert speech_tempo(original,1)==original
    slowed=speech_tempo(original,0.85)
    with wave.open(io.BytesIO(slowed)) as out:
        assert out.getframerate()==rate and out.getnchannels()==1
        samples=np.frombuffer(out.readframes(out.getnframes()),dtype=np.int16)
    assert 2.25<len(samples)/rate<2.45
    frequency=np.fft.rfftfreq(len(samples),1/rate)[np.argmax(abs(np.fft.rfft(samples)))]
    assert abs(frequency-440)<3
    with pytest.raises(ValueError):speech_tempo(original,float('nan'))
