type PlaybackState = 'idle' | 'preparing' | 'playing' | 'ended'

/** Owns exactly one synthesis/playback; stale fetches and events cannot play. */
export class LocalPlayback {
  private version = 0
  private controller: AbortController | null = null
  private player: HTMLAudioElement | null = null
  private url = ''
  constructor(private synthesize: (text: string, signal: AbortSignal, language: string) => Promise<Blob>, private state: (value: PlaybackState) => void) {}

  stop(notify = true) {
    ++this.version
    this.controller?.abort(); this.controller = null
    if (this.player) {
      this.player.onended = null; this.player.onerror = null
      this.player.pause(); this.player = null
    }
    if (this.url) URL.revokeObjectURL(this.url)
    this.url = ''
    if (notify) this.state('idle')
  }

  async play(text: string, language: string) {
    this.stop(false)
    const version = this.version, controller = new AbortController()
    this.controller = controller; this.state('preparing')
    try {
      const blob = await this.synthesize(text, controller.signal, language)
      if (version !== this.version || controller.signal.aborted) return false
      this.url = URL.createObjectURL(blob)
      const player = new Audio(this.url); this.player = player
      player.onended = () => { if (version === this.version) { this.stop(false); this.state('ended') } }
      player.onerror = () => { if (version === this.version) this.stop() }
      await player.play()
      if (version !== this.version) return false
      this.state('playing'); return true
    } catch (error) {
      if (version !== this.version || controller.signal.aborted) return false
      this.stop(); throw error
    }
  }
}
