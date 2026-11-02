const SIZE=Object.freeze({width:112,height:128})
function fit(bounds,area){
  const width=Math.min(bounds.width,area.width),height=Math.min(bounds.height,area.height)
  return {x:Math.round(Math.max(area.x,Math.min(bounds.x,area.x+area.width-width))),y:Math.round(Math.max(area.y,Math.min(bounds.y,area.y+area.height-height))),width,height}
}
function bounce(bounds,area,direction,step=2){
  const fitted=fit(bounds,area),margin=Math.min(6,Math.max(0,(area.width-fitted.width)/2)),left=area.x+margin,right=area.x+area.width-fitted.width-margin
  if(right<=left)return {bounds:{...fitted,x:Math.round(left)},direction:direction<0?-1:1,turned:false}
  let dir=direction<0?-1:1,x=Math.max(left,Math.min(fitted.x,right))+dir*Math.min(Math.abs(step),(right-left)/2),turned=false
  if(dir>0&&x>=right){x=right-Math.max(0,x-right);dir=-1;turned=true}
  else if(dir<0&&x<=left){x=left+Math.max(0,left-x);dir=1;turned=true}
  return {bounds:{...fitted,x:Math.round(Math.max(left,Math.min(x,right)))},direction:dir,turned}
}
function chatPlacement(pet,area){
  const width=Math.min(420,area.width),height=Math.min(490,area.height)
  return fit({x:pet.x+pet.width-width,y:pet.y-height-10,width,height},area)
}
function robotShape(){
  // Tight native input/paint region around the SVG silhouette, in DIP. These
  // bands include a small animation margin, never a window-sized rectangle.
  const inside=(x,y)=>{
    const px=(x-6)*1.6,py=(y-2)*1.6
    const head=px>=29&&px<=131&&py>=28&&py<=99&&((Math.max(53-px,0,px-107))**2+(Math.max(52-py,0,py-75))**2<=27**2)
    return head||(px>=70&&px<=90&&py>=2&&py<=35)||(px>=44&&px<=116&&py>=98&&py<=140)||(px>=24&&px<=53&&py>=99&&py<=132)||(px>=110&&px<=155&&py>=61&&py<=117)||(px>=47&&px<=113&&py>=131&&py<=153)||(x>=22&&x<=91&&y>=105&&y<=123)
  }
  const rects=[]
  for(let y=0;y<SIZE.height;y+=2){let start=-1;for(let x=0;x<=SIZE.width;x++){const hit=x<SIZE.width&&inside(x,y);if(hit&&start<0)start=x;if(!hit&&start>=0){rects.push({x:start,y,width:x-start,height:2});start=-1}}}
  return rects
}
module.exports={SIZE,fit,bounce,chatPlacement,robotShape}
