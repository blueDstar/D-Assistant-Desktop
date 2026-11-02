;(function(scope){
  async function completeSpokenReply(result,{display,speak,complete,isCurrent=()=>true}){
    display(result.message)
    const spoken=await speak(result.message)
    if(!spoken||!isCurrent())return false
    if(result.action_id){const receipt=await complete(result.action_id);if(isCurrent())display(result.message+'\n'+receipt.message)}
    return isCurrent()
  }
  if(typeof module!=='undefined')module.exports={completeSpokenReply};else scope.completeSpokenReply=completeSpokenReply
})(globalThis)
