// Read visible reply cards only inside the column containing the exact root.
// The browser page is never modified by this extractor.
(code) => {
  const region = Array.from(document.querySelectorAll('[role="region"],main,[role="main"]')).find(r =>
    Array.from(r.querySelectorAll('a[href]')).some(a => a.getAttribute('href')?.split(/[?#]/)[0].endsWith('/post/'+code)));
  if (!region) return [];
  const rows=[];
  const cards=Array.from(region.querySelectorAll('[data-pressable-container="true"]'));
  const relatedLabels=new Set(['Related threads','Related posts','Thread liên quan','Các thread liên quan','Bài viết liên quan']);
  const related=Array.from(region.querySelectorAll('*')).find(e=>!e.children.length&&relatedLabels.has(e.textContent.trim()));
  for(const card of cards){
    if(related && (related.compareDocumentPosition(card)&Node.DOCUMENT_POSITION_FOLLOWING))continue;
    // Do not traverse nested pressable cards twice.
    if(card.parentElement?.closest('[data-pressable-container="true"]'))continue;
    const time=card.querySelector('time');
    const permalink=time?.closest('a[href*="/post/"]');
    if(!permalink)continue;
    const href=permalink.getAttribute('href');
    if(href.split(/[?#]/)[0].endsWith('/post/'+code))continue;
    // Stop at an explicitly marked recommendation section if present.
    let section=card.closest('section');
    if(section&&/suggested|recommended|đề xuất|gợi ý/i.test(section.getAttribute('aria-label')||''))continue;
    const authorLink=Array.from(card.querySelectorAll('a[href]')).find(a=>/^\/@[^/]+\/?$/.test(a.getAttribute('href'))&&a.innerText.trim());
    const parts=[];
    for(const span of card.querySelectorAll('span[dir="auto"]')){
      if(span.closest('a,button,time,[role="button"]'))continue;
      const copy=span.cloneNode(true);
      copy.querySelectorAll('button,[role="button"],a,time').forEach(e=>e.remove());
      const text=copy.textContent.trim();
      if(text&&!/^[\d\s.,KMNBkmnb]+$/.test(text))parts.push(text);
    }
    const text=parts.sort((a,b)=>b.length-a.length)[0]||'';
    const has_media=Array.from(card.querySelectorAll('img,video')).some(el=>el.tagName==='VIDEO'||(!el.closest('a[href^="/@"]:not([href*="/post/"])')&&!/avatar|profile picture|ảnh đại diện/i.test(el.alt||'')));
    if((!text&&!has_media)||!authorLink)continue;
    const like=Array.from(card.querySelectorAll('[role="button"],button')).find(b=>
      /^(Like|Thích)(\s|$)/.test(b.getAttribute('aria-label')||'') ||
      Array.from(b.querySelectorAll('svg title')).some(t=>/^(Like|Thích)$/.test(t.textContent.trim())));
    const raw=like?.innerText.trim()||'';
    const number=parseFloat(raw.replace(',','.'));
    const likes=Number.isFinite(number)?Math.round(number*(/[kK]/.test(raw)?1000:/[mM]/.test(raw)?1000000:1)):0;
    rows.push({id:href,author:authorLink.innerText.trim(),text,has_media,likes,likes_display:raw,
      comment_url:new URL(href,location.origin).href,
      capture_selector:'a[href='+JSON.stringify(href)+']:has(time)',capture_index:0,
      capture_parent:'ancestor::*[@data-pressable-container="true"][1]'});
  }
  return rows;
}
