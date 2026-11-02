class DbotRecorder extends AudioWorkletProcessor {
  constructor() { super(); this.frames = []; this.size = 0; this.batch = Math.round(sampleRate / 10) }
  process(inputs) {
    const input = inputs[0]?.[0]
    if (input) {
      this.frames.push(new Float32Array(input)); this.size += input.length
      if (this.size >= this.batch) {
        const frame = new Float32Array(this.size); let offset = 0
        for (const part of this.frames) { frame.set(part, offset); offset += part.length }
        this.port.postMessage(frame, [frame.buffer]); this.frames = []; this.size = 0
      }
    }
    return true
  }
}
registerProcessor('dbot-recorder', DbotRecorder)
