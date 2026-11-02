/** Local energy endpointing, shared by main chat and the desktop companion. */
export class VoiceActivity {
  silenceMs: number; maxWaitMs: number; maxTurnMs: number; threshold: number; speechMs: number
  elapsed=0; quiet=0; voiced=0; started=false; done=false; noise=0.002; peak=0
  private calibration: number[]=[]
  constructor({silenceMs=750,maxWaitMs=12000,maxTurnMs=25000,threshold=0.006,speechMs=90}={}) {
    Object.assign(this,{silenceMs,maxWaitMs,maxTurnMs,threshold,speechMs})
    this.silenceMs=silenceMs;this.maxWaitMs=maxWaitMs;this.maxTurnMs=maxTurnMs;this.threshold=threshold;this.speechMs=speechMs
  }
  reset(){this.elapsed=0;this.quiet=0;this.voiced=0;this.started=false;this.done=false;this.noise=.002;this.peak=0;this.calibration=[]}
  feed(level:number,ms:number):{started?:boolean;finished?:boolean;silence?:boolean}|null {
    if(this.done||!Number.isFinite(level)||!Number.isFinite(ms)||ms<=0)return null
    this.elapsed+=ms
    // Buffer the opening words while measuring the background; a clear onset
    // can start immediately. This is an energy heuristic, not speaker ID.
    if(!this.started&&this.elapsed<=240&&level<.04){
      this.calibration.push(level)
      const ordered=[...this.calibration].sort((a,b)=>a-b)
      this.noise=Math.max(.001,ordered[Math.floor((ordered.length-1)*.2)]||.001)
      return {}
    }
    const onset=Math.max(this.threshold,this.noise*2.2)
    const offset=Math.max(this.threshold*.65,this.noise*1.5,this.peak*.32)
    const speech=level>=(this.started?offset:onset)
    let justStarted=false
    if(speech){
      this.voiced+=ms;this.quiet=0;this.peak=Math.max(this.peak,level)
      if(!this.started&&this.voiced>=this.speechMs){this.started=true;justStarted=true}
    }else{
      this.quiet+=ms
      if(!this.started){this.voiced=0;this.noise=this.noise*.9+level*.1}
    }
    const finished=this.started&&(this.quiet>=this.silenceMs||this.elapsed>=this.maxTurnMs)
    const silence=!this.started&&this.elapsed>=this.maxWaitMs
    if(finished||silence){this.done=true;return {finished,silence}}
    return justStarted?{started:true}:{}
  }
}
