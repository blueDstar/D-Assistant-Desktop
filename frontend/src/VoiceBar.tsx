export function VoiceBar({ voice, disabled }: any) {
  return <div className={`voice-bar ${voice.callActive ? 'active' : ''}`}>
    <div><strong>Hội thoại bằng giọng nói</strong><small role="status">{voice.callActive ? voice.callState : 'Whisper + Piper local · tự gửi sau khi bạn ngừng nói'}</small></div>
    {voice.callActive && <meter aria-label="Mức microphone" min={0} max={1} value={voice.micLevel} />}
    <div className="row-actions">{voice.callActive ? <><button disabled={voice.callTranscribing||voice.speaking||voice.synthesizing||disabled} onClick={voice.finishUtterance}>Xong, gửi</button><button onClick={() => void voice.interrupt()}>Ngắt & nói</button><button onClick={() => voice.stopConversation()}>Kết thúc</button></> : <button disabled={disabled} onClick={() => void voice.startConversation()}>Bắt đầu nói chuyện</button>}</div>
    {voice.callActive && <label className="voice-barge"><input type="checkbox" checked={voice.bargeIn} onChange={e => voice.setBargeIn(e.target.checked)} />Thử ngắt khi tôi nói (dùng tai nghe; chưa kiểm tra mic thật)</label>}
  </div>
}
