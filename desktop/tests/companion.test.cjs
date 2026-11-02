const {test}=require('node:test'),assert=require('node:assert/strict'),{EventEmitter}=require('node:events')
const {SIZE,bounce,fit,chatPlacement,robotShape}=require('../pet-geometry.cjs'),{Companion}=require('../companion.cjs')
const area={x:-1280,y:0,width:1280,height:900}
class Window extends EventEmitter{
 constructor(options){super();this.options=options;this.bounds={x:options.x,y:options.y,width:options.width,height:options.height};this.ignored=[]}
 setBounds(b){this.bounds={...b}} getBounds(){return {...this.bounds}} setShape(value){this.shape=value}
 setPosition(x,y){this.bounds={...this.bounds,x,y}}
 setIgnoreMouseEvents(v){this.ignored.push(v)} show(){} showInactive(){} focus(){} hide(){this.emit('hide')} isDestroyed(){return false}
}
function setup(settings={}){let time=0;const screen=Object.assign(new EventEmitter(),{getDisplayMatching:()=>({workArea:area}),getPrimaryDisplay:()=>({workArea:area}),getDisplayNearestPoint:()=>({workArea:area}),getCursorScreenPoint:()=>({x:-50,y:800})});const c=new Companion({BrowserWindow:Window,screen,directory:__dirname,settings:{roaming:true,petVisible:true,...settings},save(){},onChange(){},secure(){},log(){},now:()=>time});return {c,time:t=>time=t}}
test('both screen edges reverse once and then move away',()=>{
 for(const [x,direction] of [[-112,1],[-1280,-1]]){let b={x,y:700,...SIZE},d=direction,turns=0;for(let i=0;i<12;i++){const n=bounce(b,area,d);if(n.turned)turns++;b=n.bounds;d=n.direction}assert.equal(turns,1);assert.equal(d,-direction);assert.ok(b.x>-1274&&b.x<-118)}
})
test('small displays and negative coordinates fit chat and pet',()=>{for(const a of [area,{x:200,y:-200,width:80,height:90}]){const b=fit({x:9000,y:-9000,...SIZE},a),p=chatPlacement(b,a);for(const r of [b,p]){assert.ok(r.x>=a.x&&r.y>=a.y);assert.ok(r.x+r.width<=a.x+a.width&&r.y+r.height<=a.y+a.height)}}})
test('chat never enlarges transparent pet or disables default pass through',()=>{const {c}=setup();assert.equal(c.pet.options.focusable,false);assert.equal(c.chat.options.transparent,false);assert.equal(c.chat.options.alwaysOnTop,false);for(let i=0;i<6;i++){c.setPanel(true);c.tick();c.setPanel(false)}assert.deepEqual(c.pet.ignored,[true]);assert.equal(c.pet.getBounds().width,112);assert.equal(c.pet.getBounds().height,128)})
test('pointer at edge does not freeze movement; optional input shape has no full rectangle',()=>{const {c}=setup();c.pet.setBounds({x:-112,y:750,...SIZE});for(let i=0;i<12;i++)c.tick();assert.ok(c.pet.getBounds().x<-125);c.setPanel(true);c.setClickThrough(false);c.setClickThrough(true);assert.deepEqual(c.pet.ignored,[true,false,true]);assert.ok(robotShape().length>20);assert.ok(robotShape().every(r=>r.width<SIZE.width))})
test('activity expressions expire and validate; dragged pet only pauses temporarily',()=>{const {c,time}=setup({roaming:false,clickThrough:false});time(3000);c.setMood('listening');assert.equal(c.mood(),'listening');c.setMood('happy');assert.equal(c.mood(),'happy');time(5000);assert.equal(c.mood(),'idle');time(60000);assert.equal(c.mood(),'sleeping');assert.throws(()=>c.preview('../bad'));c.move(5,0);assert.equal(c.pauseUntil,61200)})

test('hidden robot recovers from an unexpected native oversized window',()=>{const {c}=setup({petVisible:false});c.pet.bounds={x:0,y:0,width:1528,height:624};c.tick();assert.equal(c.pet.getBounds().width,112);assert.equal(c.pet.getBounds().height,128);assert.equal(c.pet.options.maximizable,false)})
