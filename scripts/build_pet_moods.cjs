const fs=require('node:fs'),path=require('node:path')
const folder=path.join(__dirname,'..','desktop','expressions'),base=fs.readFileSync(path.join(folder,'..','robot.svg'),'utf8')
const eyes={
 idle:'<rect x="55" y="54" width="11" height="17" rx="5.5"/><rect x="94" y="54" width="11" height="17" rx="5.5"/>',
 walking:'<rect x="57" y="54" width="10" height="17" rx="5"/><rect x="96" y="54" width="10" height="17" rx="5"/>',
 greeting:'<path d="m54 64 7-8 7 8m24 0 7-8 7 8" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>',
 listening:'<circle cx="61" cy="61" r="9"/><circle cx="99" cy="61" r="9"/><circle cx="63" cy="60" r="3" fill="#141414"/><circle cx="101" cy="60" r="3" fill="#141414"/>',
 thinking:'<rect x="58" y="51" width="10" height="15" rx="5"/><rect x="97" y="51" width="10" height="15" rx="5"/><path d="M54 47h16m22 0h16" stroke="currentColor" stroke-width="2"/>',
 speaking:'<rect x="55" y="54" width="11" height="17" rx="5.5"/><rect x="94" y="54" width="11" height="17" rx="5.5"/>',
 question:'<rect x="55" y="56" width="11" height="14" rx="5"/><rect x="94" y="50" width="11" height="20" rx="5"/><path d="m92 45 15-3" stroke="currentColor" stroke-width="2"/>',
 happy:'<path d="M53 65q8-18 16 0m22 0q8-18 16 0" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>',
 error:'<path d="m54 52 14 6m24 0 14-6" stroke="currentColor" stroke-width="3"/><circle cx="61" cy="65" r="5"/><circle cx="99" cy="65" r="5"/>',
 sleeping:'<path d="M53 63q8 8 16 0m22 0q8 8 16 0" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>'
}
const mouths={idle:'M73 76q7 5 14 0',walking:'M73 76q7 6 14 0',greeting:'M70 74q10 12 20 0Z',listening:'M76 77h8',thinking:'M76 77h12',speaking:'M73 73q7-5 14 0v5q-7 6-14 0Z',question:'M74 77q7-4 14 0',happy:'M69 73q11 15 22 0Z',error:'M73 80q7-8 14 0',sleeping:'M77 77h6'}
fs.mkdirSync(folder,{recursive:true})
for(const [name,eye] of Object.entries(eyes)){
 const styles=`.eye{color:#F3F0E9}${name==='walking'?'':'.bootL,.bootR{animation:none}'}${name==='greeting'?'':'.arm{animation:none}'}${name==='speaking'?'.mouth{transform-origin:80px 76px;animation:talk .35s infinite alternate}@keyframes talk{to{transform:scaleY(.4)}}':''}${name==='sleeping'?'.eye{animation:none}.float{animation-duration:5s}':''}`
 const svg=base.replace('</style>',styles+'</style>').replace(/<g class="eye"[\s\S]*?<\/g>/,`<g class="eye" fill="#F3F0E9">${eye}</g>`).replace('<path d="M73 76q7 5 14 0"',`<path class="mouth" d="${mouths[name]}"`)
 fs.writeFileSync(path.join(folder,name+'.svg'),svg)
}
console.log('Generated 10 local SVG expressions')
