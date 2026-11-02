"""Pitch-preserving tempo for PCM speech, entirely in memory via bundled PyAV."""
import io
import math
import wave
from fractions import Fraction

def speech_tempo(wav_bytes:bytes,speed:float)->bytes:
    if not math.isfinite(speed) or not 0.5<=speed<=2:raise ValueError('Tốc độ giọng nói không hợp lệ')
    if speed==1:return wav_bytes
    import av
    import numpy as np
    with wave.open(io.BytesIO(wav_bytes),'rb') as source:
        if source.getnchannels()!=1 or source.getsampwidth()!=2:raise ValueError('Cần PCM mono 16-bit')
        rate=source.getframerate();pcm=source.readframes(source.getnframes())
    frame=av.AudioFrame.from_ndarray(np.frombuffer(pcm,dtype=np.int16).reshape(1,-1),format='s16',layout='mono')
    frame.sample_rate=rate;frame.time_base=Fraction(1,rate);frame.pts=0
    graph=av.filter.Graph();input_node=graph.add_abuffer(sample_rate=rate,format='s16',layout='mono',time_base=Fraction(1,rate));tempo=graph.add('atempo',str(speed));output_format=graph.add('aformat','sample_fmts=s16:channel_layouts=mono');sink=graph.add('abuffersink')
    input_node.link_to(tempo);tempo.link_to(output_format);output_format.link_to(sink);graph.configure()
    input_node.push(frame);input_node.push(None);chunks=[]
    while True:
        try:chunks.append(sink.pull().to_ndarray().astype(np.int16,copy=False).tobytes())
        except (av.error.EOFError,av.error.BlockingIOError):break
    if not chunks:raise ValueError('Không tạo được âm thanh sau điều chỉnh tốc độ')
    output=io.BytesIO()
    with wave.open(output,'wb') as destination:
        destination.setnchannels(1);destination.setsampwidth(2);destination.setframerate(rate);destination.writeframes(b''.join(chunks))
    return output.getvalue()
