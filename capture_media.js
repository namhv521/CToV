// Prepare only the target card. Do not play or download attached videos.
async el => {
  const attachments=Array.from(el.querySelectorAll('img,video')).filter(node=>
    node.tagName==='VIDEO'||(!node.closest('a[href^="/@"]:not([href*="/post/"])')&&
    !node.closest('[data-e2e*="avatar"]')&&!/avatar|profile picture|ảnh đại diện/i.test(node.alt||'')));
  const deadline=Date.now()+4000;
  const posters=new Map();
  for(const node of attachments){
    node.scrollIntoView({block:'nearest',inline:'nearest'});
    if(node.tagName==='VIDEO'&&node.poster){
      const poster=new Image();poster.src=node.poster;posters.set(node,poster);
    }
  }
  const ready=node=>node.tagName==='IMG' ? node.complete&&node.naturalWidth>0 :
    node.readyState>=2||(posters.get(node)?.complete&&posters.get(node).naturalWidth>0);
  while(attachments.some(node=>!ready(node))&&Date.now()<deadline){
    await new Promise(resolve=>setTimeout(resolve,100));
  }
  // Decode image pixels rather than trusting a completed network response.
  await Promise.race([
    Promise.all(Array.from(el.querySelectorAll('img')).map(im=>im.decode().catch(()=>{}))),
    new Promise(resolve=>setTimeout(resolve,500))
  ]);
  if(!el.isConnected||attachments.some(node=>!el.contains(node)))throw Error('Thẻ bình luận đã thay đổi trong lúc chụp. Hãy crawl lại.');
  return {has_media:attachments.length>0,missing:attachments.filter(node=>!ready(node)).length};
}
