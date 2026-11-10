// Locate only the exact original post, never a reply or recommendation.
source => {
  const url=new URL(source);
  const threads=/threads\.(com|net)$/.test(url.hostname);
  let card,anchor;
  if(threads){
    const code=url.pathname.match(/\/(?:post|t)\/([^/]+)/)?.[1];
    anchor=Array.from(document.querySelectorAll('a[href]')).find(a=>{
      try{return new URL(a.href).pathname.split('/').pop()===code&&a.querySelector('time');}catch{return false;}
    });
    card=anchor?.closest('[data-pressable-container="true"]');
  }else{
    const desc=document.querySelector('[data-e2e="browse-video-desc"]');
    for(let node=desc?.parentElement;node&&node!==document.body;node=node.parentElement){
      if(node.querySelector('[data-e2e="comment-item"],[data-e2e="comment-list"]'))break;
      if(node.querySelector('video')){card=node;break;}
    }
  }
  if(!card)return null;
  const author=card.querySelector('[data-e2e="browse-username"]')||Array.from(card.querySelectorAll('a[href]')).find(a=>/^\/@[^/]+\/?$/.test(a.getAttribute('href')||'')&&a.innerText.trim());
  const parts=threads?Array.from(card.querySelectorAll('span[dir="auto"]'))
    .filter(s=>!s.closest('a,button,time,[role="button"],[aria-hidden="true"],[contenteditable="true"]')&&!s.querySelector('time,span[dir="auto"]'))
    .map(s=>{
      // Timestamp wrappers and nested Translate controls are UI, not speech.
      const copy=s.cloneNode(true);
      copy.querySelectorAll('button,time,[role="button"],[aria-hidden="true"],[contenteditable="true"]').forEach(node=>node.remove());
      copy.querySelectorAll('br').forEach(node=>node.replaceWith('\n'));
      return copy.textContent.trim();
    }).filter(Boolean):[card.querySelector('[data-e2e="browse-video-desc"]')?.innerText||''];
  const text=Array.from(new Set(parts)).join('\n').trim();
  if(!text&&!card.querySelector('img,video'))return null;
  const row={id:source,author:author?.innerText.trim()||'',text,comment_url:source,capture_zoom:1.25};
  // Threads can replace the root card during hydration. Resolve it again by permalink.
  if(threads)return {...row,
    capture_selector:'a[href='+JSON.stringify(anchor.getAttribute('href'))+']:has(time)',
    capture_parent:'ancestor::*[@data-pressable-container="true"][1]'};
  card.setAttribute('data-commentcut-original','true');
  return {...row,capture_selector:'[data-commentcut-original="true"]'};
}
