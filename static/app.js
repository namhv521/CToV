'use strict';
const $ = id => document.getElementById(id);
let library = [], project = freshProject(), activeJob = null, activeBatch = null, dirty = false;
let crawlDays = [], selectedDay = '';
let previewTimer, cardUrl, voiceUrl, noticeTimer, previewSequence = 0;
const newId = () => crypto.randomUUID().replaceAll('-', '');
function freshProject(){ return {id:crypto.randomUUID().replaceAll('-',''),name:'Video chưa đặt tên',url:'',post:'',post_image:'',post_captured_at:'',post_capture_error:'',author:'',comments:[],crawl_note:'',crawled_at:'',crawl_date:'',options:{provider:'google',voice:'vi-VN-HoaiMyNeural',speed:1.1,elevenlabs_voices:[''],use_meme_image:true,use_meme_sound:true,resolution:720,background:'',default_meme:'',default_sound:'',credit:'CRE: COMMENTCUT',card_y:.28,max_seconds:120,split_mode:'comments',video_count:3,comments_per_video:10,read_post:true,anonymous:false,meme_volume:.65}}; }
const optionIds = {provider:'provider',voice:'voice',use_meme_image:'use-meme-image',use_meme_sound:'use-meme-sound',speed:'speed',resolution:'resolution',background:'background',default_meme:'default-meme',default_sound:'default-sound',credit:'credit',card_y:'card-y',max_seconds:'max-seconds',split_mode:'split-mode',video_count:'video-count',comments_per_video:'comments-per-video',read_post:'read-post',anonymous:'anonymous',meme_volume:'meme-volume'};
const numeric = new Set(['speed','resolution','card_y','max_seconds','meme_volume','video_count','comments_per_video']);
function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function notice(text,error=false){clearTimeout(noticeTimer);$('notice').textContent=text;$('notice').className=error?'error':'';$('notice').hidden=false;noticeTimer=setTimeout(()=>$('notice').hidden=true,error?16000:7000);}
async function api(path, options={}){const r=await fetch(path,options);if(!r.ok){let value;try{value=await r.json();}catch{throw Error(`Lỗi HTTP ${r.status}`);}throw Error(typeof value.detail==='string'?value.detail:'Dữ liệu không hợp lệ. Kiểm tra nội dung và giới hạn ký tự.');}return r;}
const json = async(path,body)=> (await api(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
async function busy(button, task){const old=button.textContent;button.disabled=true;try{return await task();}catch(e){notice(e.message,true);}finally{button.disabled=false;button.textContent=old;}}
function touch(){dirty=true;updateScriptPlan();clearTimeout(previewTimer);previewTimer=setTimeout(updatePreview,550);}
function sync(){project.name=$('project-name').value.trim()||'Video chưa đặt tên';project.url=$('source-url').value.trim();project.post=$('post-text').value;project.author=$('post-author').value;for(const [key,id]of Object.entries(optionIds)){const e=$(id);project.options[key]=e.tagName==='BUTTON'?e.getAttribute('aria-pressed')==='true':e.type==='checkbox'?e.checked:numeric.has(key)?Number(e.value):e.value;}project.options.elevenlabs_voices=Array.from($('eleven-voice-fields').querySelectorAll('input'), input=>input.value.trim());$('current-name').textContent=project.name;return project;}
function fill(){ project.options={...freshProject().options,...project.options};$('project-name').value=project.name;$('source-url').value=project.url;$('post-text').value=project.post;$('post-author').value=project.author;$('crawl-note').textContent=project.crawl_note||'Tên dự án tự đặt theo nội dung bài gốc khi đang để mặc định. Bạn luôn có thể sửa lại bên dưới.';for(const[key,id]of Object.entries(optionIds)){const e=$(id);if(e.tagName==='BUTTON'){e.setAttribute('aria-pressed',String(project.options[key]));e.textContent=e.dataset.label+': '+(project.options[key]?'Bật':'Tắt');}else if(e.type==='checkbox')e.checked=project.options[key];else e.value=project.options[key];}const voices=project.options.elevenlabs_voices;drawVoiceFields(voices.length===3&&!voices.some(Boolean)?['']:voices);$('current-name').textContent=project.name;drawPostCapture();drawComments();changeBackground();updatePreview();updateScriptPlan();}
function drawPostCapture(){
 const wrap=$('post-capture');wrap.replaceChildren();
 $('post-text').readOnly=!!(project.post_image&&project.post_captured_at);
 $('post-author').readOnly=$('post-text').readOnly;
 if(project.post_image){const link=node('a');link.href=`/api/assets/${project.post_image}/file`;link.target='_blank';link.rel='noopener';const image=node('img');image.src=link.href;image.alt='Ảnh chụp thật bài viết gốc';link.append(image);wrap.append(link,node('p','help','Ảnh bài viết gốc · dùng trực tiếp cho đoạn mở đầu. Bấm ảnh để xem đầy đủ.'));}
 else wrap.append(node('p','help',project.post_capture_error||'Chưa có ảnh bài gốc. Crawl nguồn để chụp thật; không dựng thẻ chữ thay thế.'));
}
function assetOptions(select,kind,mode='default',value=''){
 select.replaceChildren();const first=node('option','',mode==='background'?'Ngẫu nhiên từ data/Vid_nen':mode==='image'?'Dựng ảnh từ văn bản':mode==='meme'?'Theo mặc định':'Theo mặc định');first.value='';select.append(first);
 if(mode!=='background'&&mode!=='image'){const off=node('option','','Không dùng');off.value='none';select.append(off);}
 for(const item of library.filter(a=>a.kind===kind&&(mode!=='meme'||!['comment_capture','post_capture'].includes(a.role)))){const o=node('option','',item.name);o.value=item.id;select.append(o);}
 if(value&&!Array.from(select.options).some(o=>o.value===value)){const missing=node('option','','Tài sản thiếu — hãy chọn lại');missing.value=value;select.append(missing);}
 select.value=value;
}
function detailField(container,labelText,control,wide=false){const wrap=node('div',wide?'wide':'');const id='field-'+newId();control.id=id;const label=node('label','',labelText);label.htmlFor=id;wrap.append(label,control);container.append(wrap);}
function commentDefaults(c){return {id:newId(),author:'Người dùng',text:'',speech:'',likes:0,selected:true,meme:'',sound:'',image:'',meme_seconds:1.2,...c};}
function drawComments(){
 updateScriptPlan();const list=$('comments');list.replaceChildren();$('comment-count').textContent=`${project.comments.filter(c=>c.selected).length}/${project.comments.length}`;
 if(!project.comments.length){const empty=node('div','empty-script');empty.append(node('strong','','Một câu chuyện bắt đầu từ một bình luận.'),node('span','','Dán link ở trên, chọn file .txt hàng loạt hoặc thêm kịch bản của bạn bên dưới.'));list.append(empty);return;}
 project.comments.forEach((c,index)=>{
  const row=node('article','comment'),head=node('div','comment-head');
  const check=node('input');check.type='checkbox';check.checked=c.selected;check.setAttribute('aria-label',`Chọn bình luận ${index+1}`);check.addEventListener('change',()=>{c.selected=check.checked;$('comment-count').textContent=`${project.comments.filter(x=>x.selected).length}/${project.comments.length}`;touch();});
  const author=node('input');author.type='text';author.value=c.author;author.maxLength=100;author.setAttribute('aria-label',`Tác giả bình luận ${index+1}`);author.addEventListener('input',()=>{c.author=author.value;touch();});
  const likeLabel=node('label','','Lượt thích');const like=node('input');like.type='number';like.min=0;like.value=c.likes;like.id='likes-'+c.id;likeLabel.htmlFor=like.id;like.setAttribute('aria-label',`Lượt thích bình luận ${index+1}`);like.addEventListener('input',()=>{c.likes=Math.max(0,Number(like.value)||0);touch();});
  const tools=node('div','comment-tools');for(const [label,symbol,action,disabled]of[
   ['Đưa bình luận lên','↑',()=>{[project.comments[index-1],project.comments[index]]=[c,project.comments[index-1]];},index===0],
   ['Đưa bình luận xuống','↓',()=>{[project.comments[index+1],project.comments[index]]=[c,project.comments[index+1]];},index===project.comments.length-1],
   ['Xóa bình luận','×',()=>{project.comments.splice(index,1);},false]]){const b=node('button','',symbol);b.title=label;b.setAttribute('aria-label',label);b.disabled=disabled;b.addEventListener('click',()=>{action();drawComments();touch();});tools.append(b);}
  head.append(check,author,likeLabel,like,tools);
  const text=node('textarea');text.rows=2;text.maxLength=1500;text.value=c.text;text.setAttribute('aria-label',`Nội dung bình luận ${index+1}`);text.addEventListener('input',()=>{c.text=text.value;touch();});
  let captureBlock;
  if(c.captured_at&&c.image){
   captureBlock=node('div','captured-comment');
   const link=node('a');link.href=`/api/assets/${c.image}/file`;link.target='_blank';link.rel='noopener';
   const shot=node('img');shot.src=link.href;shot.alt=`Ảnh chụp bình luận thật của ${c.author}`;shot.loading='lazy';link.append(shot);
   const caption=node('p','help',`Ảnh gốc · ${new Date(c.captured_at).toLocaleString('vi-VN')}${c.likes_display?' · '+c.likes_display+' tim hiển thị':''}. Bấm ảnh để xem đầy đủ.`);
   const hint=node('p','help',c.text?'Chữ bên dưới được lấy từ thẻ trong ảnh để đọc giọng. Muốn sửa phát âm, mở Lời đọc riêng.':'Bình luận chỉ có ảnh/video: hiển thị ảnh chụp 3 giây, không đọc giọng. Có thể thêm Lời đọc riêng.');
   captureBlock.append(link,caption,hint);text.readOnly=true;author.readOnly=true;like.readOnly=true;like.type='text';like.value=c.likes_display||'Xem ảnh';likeLabel.textContent='Tim thật';
  }
  const details=node('details');details.append(node('summary','',`Ảnh chụp & lời đọc riêng`));const fields=node('div','comment-details');
  const speech=node('textarea');speech.rows=2;speech.maxLength=1500;speech.placeholder='Để trống để đọc nguyên văn bình luận';speech.value=c.speech||'';speech.addEventListener('input',()=>{c.speech=speech.value;touch();});detailField(fields,'Lời đọc (có thể viết rõ từ viết tắt)',speech,true);
  for(const[key,label,kind,mode]of[['image','Ảnh chụp thay bình luận','image','image']]){const s=node('select');assetOptions(s,kind,mode,c[key]);s.addEventListener('change',()=>{c[key]=s.value;touch();});detailField(fields,label,s);}
  details.append(fields);row.append(head);if(captureBlock)row.append(captureBlock);row.append(text,details);list.append(row);
 });
}
async function updatePreview(){const sequence=++previewSequence;try{sync();const r=await api('/api/card-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(project)});const blob=await r.blob();if(sequence!==previewSequence)return;if(cardUrl)URL.revokeObjectURL(cardUrl);cardUrl=URL.createObjectURL(blob);$('card-preview').src=cardUrl;}catch(e){if(sequence===previewSequence)notice(e.message,true);}}
function changeBackground(){const id=$('background').value||library.find(a=>a.source_folder==='Vid_nen')?.id;const v=$('background-preview');$('preview-empty').hidden=!!id;if(id){const src=`/api/assets/${id}/file`;if(v.getAttribute('src')!==src){v.src=src;v.play().catch(()=>{});}}else{v.removeAttribute('src');v.load();}}
async function loadAssets(){library=await(await api('/api/assets')).json();$('asset-count').textContent=library.length;assetOptions($('background'),'background','background',project.options.background);assetOptions($('default-meme'),'image','meme',project.options.default_meme);$('default-meme').options[0].textContent='Ảnh chữ minh họa';assetOptions($('default-sound'),'sound','sound',project.options.default_sound);$('default-sound').options[0].textContent='Không âm thanh';drawLibrary();drawComments();changeBackground();}
function drawLibrary(){const list=$('asset-list');list.replaceChildren();if(!library.length){list.append(node('p','help','Chưa có media. Thêm video nền, ảnh meme hoặc tạo bộ minh họa để dựng thử.'));return;}for(const a of library){const row=node('article','asset-item');const media=node(a.kind==='background'?'video':a.kind==='sound'?'audio':'img');media.src=`/api/assets/${a.id}/file`;if(a.kind==='image'){media.alt=a.name;media.loading='lazy';}else{media.controls=true;media.preload='metadata';if(a.kind==='background')media.muted=true;}row.append(media,node('h3','',a.name),node('p','',`${{background:'Video nền',image:'Ảnh',sound:'Âm thanh'}[a.kind]} · ${(a.bytes/1024/1024).toFixed(1)} MB${a.duration?' · '+a.duration.toFixed(1)+' giây':''}`));list.append(row);}}
async function loadProjects(){const values=await(await api('/api/projects')).json();$('open-project').replaceChildren(new Option('Chọn dự án đã lưu',''));for(const p of values)$('open-project').append(new Option(p.crawl_date?`[${p.crawl_date}] ${p.name}`:p.name,p.id));await loadCrawlDays();}

function formatDayLabel(dateStr){
 const [y,m,d]=dateStr.split('-').map(Number);
 if(!y||!m||!d)return dateStr;
 const dt=new Date(y,m-1,d);
 const today=new Date();today.setHours(0,0,0,0);
 const diff=Math.round((today-dt)/86400000);
 const prefix=diff===0?'Hôm nay · ':diff===1?'Hôm qua · ':'';
 return `${prefix}${String(d).padStart(2,'0')}/${String(m).padStart(2,'0')}/${y}`;
}

async function openProjectById(id){
 if(!id)return;
 if(dirty){sync();await json('/api/projects',project);}
 project=await(await api('/api/projects/'+id)).json();
 $('open-project').value=id;
 fill();dirty=false;
 setView('editor');
}

async function renderProjectById(id, button){
 await busy(button, async()=>{
  const loaded=await(await api('/api/projects/'+id)).json();
  const job=await json('/api/jobs',loaded);
  activeJob=job.id;
  notice(`Đã đưa "${loaded.name}" vào hàng đợi dựng.`);
  await loadCrawlDays();
  pollJob();
 });
}

async function loadCrawlDays(){
 crawlDays=await(await api('/api/crawl-days')).json();
 const totalProjects=crawlDays.reduce((s,d)=>s+d.project_count,0);
 $('day-count').textContent=crawlDays.length;
 if(crawlDays.length&&(!selectedDay||!crawlDays.some(d=>d.date===selectedDay)))selectedDay=crawlDays[0].date;
 drawCrawlDays(totalProjects);
}

function drawCrawlDays(){
 const side=$('days-list'), detail=$('day-detail');
 side.replaceChildren();detail.replaceChildren();
 if(!crawlDays.length){
  detail.append(node('div','empty-script',''),);
  detail.firstChild.append(node('strong','','Chưa có dữ liệu crawl theo ngày.'),node('span','','Hãy crawl 1 link hoặc nạp file .txt ở mục Biên tập & Crawl để các bài viết tự gom theo ngày crawl.'));
  return;
 }
 for(const day of crawlDays){
  const btn=node('button','day-card'+(day.date===selectedDay?' active':''));
  btn.type='button';
  const top=node('div','day-card-title');
  top.append(node('span','',formatDayLabel(day.date)),node('span','',`${day.project_count} bài`));
  const meta=node('div','day-card-meta',`${day.comment_count} cmt · ${day.rendered_videos} MP4 đã xuất`);
  btn.append(top,meta);
  btn.addEventListener('click',()=>{selectedDay=day.date;drawCrawlDays();});
  side.append(btn);
 }
 const active=crawlDays.find(d=>d.date===selectedDay)||crawlDays[0];
 if(!active)return;
 const header=node('p','help',`Ngày crawl ${formatDayLabel(active.date)} (${active.date}) · ${active.project_count} bài viết · ${active.comment_count} bình luận đã lưu.`);
 detail.append(header);
 const statusLabels={queued:'Đang chờ dựng',running:'Đang dựng',done:'Đã dựng xong',failed:'Lỗi dựng',cancelled:'Đã hủy',interrupted:'Bị gián đoạn'};
 for(const item of active.projects){
  const card=node('article','day-project-card');
  const head=node('div','day-project-head');
  const titleWrap=node('div');
  titleWrap.append(node('h2','',item.name));
  const timeText=item.crawled_at?new Date(item.crawled_at).toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit'}):'';
  const sub=node('p','day-project-meta',`${timeText?'Crawl lúc '+timeText+' · ':''}${item.author?'@'+item.author.replace(/^@/,'')+' · ':''}${item.selected_count}/${item.comment_count} bình luận được chọn`);
  titleWrap.append(sub);
  const badge=node('span','badge '+(item.job?item.job.status:''),item.job?statusLabels[item.job.status]||item.job.status:'Chưa dựng');
  head.append(titleWrap,badge);
  card.append(head);
  if(item.url){
   const srcLink=node('a','day-project-meta',item.url);
   srcLink.href=item.url;srcLink.target='_blank';srcLink.rel='noopener';
   card.append(srcLink);
  }
  if(item.job?.files?.length){
   const links=node('div','download-links');
   for(const file of item.job.files){
    const a=node('a','',`Tải ${file}`);
    a.href=`/api/jobs/${item.job.id}/files/${encodeURIComponent(file)}`;
    a.download=file;
    links.append(a);
   }
   card.append(links);
  }else if(item.job?.message&&item.job.status!=='done'){
   card.append(node('p','help',item.job.message));
  }
  const actions=node('div','day-project-actions');
  const openBtn=node('button','secondary','Mở biên tập');
  openBtn.type='button';
  openBtn.addEventListener('click',()=>openProjectById(item.id).catch(e=>notice(e.message,true)));
  const renderBtn=node('button','primary',item.job?.status==='done'?'Dựng lại':'Dựng ngay');
  renderBtn.type='button';
  renderBtn.disabled=!item.selected_count||['queued','running'].includes(item.job?.status);
  renderBtn.addEventListener('click',()=>renderProjectById(item.id,renderBtn));
  actions.append(openBtn,renderBtn);
  card.append(actions);
  detail.append(card);
 }
}

function scriptPlan(){
 const count=project.comments.filter(c=>c.selected).length;
 const mode=$('split-mode').value;
 if(!count)return {error:'Chọn ít nhất một bình luận.'};
 if(mode==='duration')return {count,mode,sizes:[]};
 const value=Number($(mode==='even'?'video-count':'comments-per-video').value);
 if(!Number.isInteger(value)||value<1||value>120)return {error:'Nhập số nguyên từ 1 đến 120.'};
 if(mode==='even'&&value>count)return {error:'Số video không được vượt số bình luận đang chọn.'};
 const sizes=mode==='even'?Array.from({length:value},(_,i)=>Math.floor(count/value)+(i<count%value?1:0)):Array.from({length:Math.ceil(count/value)},(_,i)=>Math.min(value,count-i*value));
 return {count,mode,sizes};
}
function updateScriptPlan(){
 const mode=$('split-mode').value;
 $('video-count-field').hidden=mode!=='even';
 $('comments-per-video-field').hidden=mode!=='comments';
 const plan=scriptPlan();
 $('script-groups').replaceChildren();
 $('script-summary').textContent=plan.error||(mode==='duration'?`${plan.count} bình luận đang chọn. Số video được tính theo thời lượng giọng đọc khi dựng.`:`${plan.count} bình luận đang chọn · tạo ${plan.sizes.length} video.`);
 $('script-summary').classList.toggle('script-error',!!plan.error);
 $('render').disabled=!!plan.error;
 if(plan.sizes){let start=1;for(const size of plan.sizes){$('script-groups').append(node('li','',`${size} bình luận · từ ${start} đến ${start+size-1}`));start+=size;}}
 document.querySelectorAll('[data-comments]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.comments)===Number($('comments-per-video').value))));
}
document.querySelectorAll('[data-comments]').forEach(button=>button.addEventListener('click',()=>{$('split-mode').value='comments';$('comments-per-video').value=button.dataset.comments;sync();touch();}));
function validate(){sync();if(project.options.read_post&&(project.post.trim()||project.post_image||project.url.trim())&&!project.post_image)throw Error('Thiếu ảnh bài gốc. Crawl lại hoặc tắt Đọc bài viết.');if(project.comments.some(c=>c.selected&&!c.image))throw Error('Có bình luận thiếu ảnh chụp thật. Crawl lại hoặc chọn ảnh; không dựng thẻ chữ thay thế.');validateVoiceFields();const plan=scriptPlan();if(plan.error)throw Error(plan.error);if(!project.comments.some(c=>c.selected))throw Error('Chọn ít nhất một bình luận.');if(project.comments.some(c=>c.selected&&!c.text.trim()&&!c.image))throw Error('Bình luận được chọn đang trống. Nhập nội dung hoặc bỏ chọn.');}
function setView(view){document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!=='view-'+view);document.querySelectorAll('.nav').forEach(e=>e.classList.toggle('active',e.dataset.view===view));if(view==='exports')loadJobs().catch(e=>notice(e.message,true));if(view==='library')loadAssets().catch(e=>notice(e.message,true));if(view==='days')loadCrawlDays().catch(e=>notice(e.message,true));}
document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
for(const id of ['project-name','source-url','post-text','post-author',...Object.values(optionIds)])$(id).addEventListener('input',()=>{sync();touch();if(id==='background')changeBackground();});
$('new-project').addEventListener('click',()=>busy($('new-project'),async()=>{if(dirty){sync();await json('/api/projects',project);}const next=freshProject();const saved=await json('/api/projects',next);project=next;fill();dirty=false;await loadProjects();notice(`Đã tạo data/project/${saved.folder}.`);}));
$('save-project').addEventListener('click',()=>busy($('save-project'),async()=>{sync();await json('/api/projects',project);dirty=false;await loadProjects();notice('Đã lưu dự án trên máy.');}));
$('open-project').addEventListener('change',async()=>{try{const id=$('open-project').value;if(!id)return;if(dirty){sync();await json('/api/projects',project);}project=await(await api('/api/projects/'+id)).json();fill();dirty=false;}catch(e){notice(e.message,true);}});
$('add-comment').addEventListener('click',()=>{if(project.comments.length>=120)return notice('Mỗi dự án tối đa 120 bình luận.',true);project.comments.push(commentDefaults());drawComments();touch();});
$('select-all').addEventListener('click',()=>{const selected=!project.comments.every(c=>c.selected);project.comments.forEach(c=>c.selected=selected);drawComments();touch();});
$('sort-likes').addEventListener('click',()=>{project.comments.sort((a,b)=>b.likes-a.likes);drawComments();touch();});

function setCrawlTab(mode){
 const single=mode==='single';
 $('tab-single-crawl').classList.toggle('active',single);
 $('tab-single-crawl').setAttribute('aria-selected',String(single));
 $('tab-batch-crawl').classList.toggle('active',!single);
 $('tab-batch-crawl').setAttribute('aria-selected',String(!single));
 $('single-crawl-pane').hidden=!single;
 $('batch-crawl-pane').hidden=single;
}
$('tab-single-crawl').addEventListener('click',()=>setCrawlTab('single'));
$('tab-batch-crawl').addEventListener('click',()=>setCrawlTab('batch'));

function parseBatchTextarea(){
 return Array.from(new Set($('batch-urls').value.split(/\r?\n/).map(s=>s.trim()).filter(s=>s&&!s.startsWith('#'))));
}
function updateBatchControls(){
 const urls=parseBatchTextarea();
 $('batch-url-count').textContent=urls.length;
 const splitMode=$('batch-split-mode').value;
 $('batch-cpv-wrap').hidden=splitMode!=='comments';
 $('batch-vcount-wrap').hidden=splitMode!=='even';
 const limit=Math.max(1,Math.min(120,Number($('batch-limit').value)||30));
 const autoRender=$('batch-auto-render').checked;
 if(!autoRender){
  $('batch-plan-hint').textContent=`Sẽ crawl tuần tự từng link (tối đa ${limit} bình luận/URL), tự đặt tên dự án theo bài gốc và gom vào mục Theo ngày crawl. Chưa tự động render.`;
 }else if(splitMode==='comments'){
  const cpv=Math.max(1,Number($('batch-comments-per-video').value)||10);
  const est=Math.ceil(limit/cpv);
  $('batch-plan-hint').textContent=`Mỗi URL lấy tối đa ${limit} bình luận → chia ${cpv} bình luận/video (tạo ${est} video nếu đủ ${limit} cmt; ít hơn vẫn dựng theo số thực tế lấy được).`;
 }else if(splitMode==='even'){
  const vc=Math.max(1,Number($('batch-video-count').value)||3);
  $('batch-plan-hint').textContent=`Mỗi URL lấy tối đa ${limit} bình luận → chia đều thành ${vc} video và tự động render.`;
 }else{
  $('batch-plan-hint').textContent=`Mỗi URL lấy tối đa ${limit} bình luận → tự chia video theo giới hạn thời lượng (${$('max-seconds').value}s/phần) và tự động render.`;
 }
}
for(const id of ['batch-urls','batch-limit','batch-split-mode','batch-comments-per-video','batch-video-count','batch-auto-render']){
 $(id).addEventListener('input',updateBatchControls);
 $(id).addEventListener('change',updateBatchControls);
}
$('batch-txt-file').addEventListener('change',async()=>{
 const file=$('batch-txt-file').files[0];
 if(!file)return;
 try{
  const form=new FormData();form.append('file',file);
  const res=await(await api('/api/batch-crawl/parse',{method:'POST',body:form})).json();
  $('batch-urls').value=res.urls.join('\n');
  updateBatchControls();
  const invalidMsg=res.invalid.length?` (${res.invalid.length} dòng không hợp lệ đã bỏ qua)`:'';
  $('batch-file-info').textContent=`Đã nạp "${file.name}": ${res.count} URL hợp lệ${invalidMsg}.`;
  notice(`Đã đọc ${res.count} URL từ ${file.name}${invalidMsg}.`,!res.count);
 }catch(e){notice(e.message,true);}
 finally{$('batch-txt-file').value='';}
});

function drawBatchStatus(batch){
 const wrap=$('batch-progress');wrap.replaceChildren();
 if(!batch)return;
 const box=node('div','batch-box');
 const head=node('div','batch-box-head');
 const statusText={queued:'Đang chờ',running:'Đang chạy',done:'Hoàn tất',failed:'Lỗi',cancelled:'Đã dừng',interrupted:'Gián đoạn'}[batch.status]||batch.status;
 head.append(node('strong','',`Lô crawl (${batch.completed}/${batch.total} link) · ${statusText}`));
 if(['queued','running'].includes(batch.status)){
  const stopBtn=node('button','quiet','Dừng crawl lô');
  stopBtn.type='button';
  stopBtn.addEventListener('click',()=>busy(stopBtn,async()=>{await json(`/api/batch-crawl/${batch.id}/cancel`,{});notice('Đã gửi yêu cầu dừng lô crawl.');}));
  head.append(stopBtn);
 }
 box.append(head,node('p','help',batch.message||''));
 if(['queued','running'].includes(batch.status)){
  const bar=node('progress');bar.max=Math.max(1,batch.total);bar.value=batch.completed;
  box.append(bar);
 }
 const ul=node('ul','batch-items');
 const itemBadges={queued:'Chờ',crawling:'Đang crawl',done:'Xong crawl',failed:'Lỗi',cancelled:'Đã hủy',interrupted:'Gián đoạn'};
 for(const [idx,it] of (batch.items||[]).entries()){
  const li=node('li');
  const top=node('div','batch-item-top');
  const label=node('strong','',`${idx+1}. ${it.name||it.url}`);
  const right=node('div','actions');
  right.append(node('span','badge '+it.status,itemBadges[it.status]||it.status));
  if(it.job){
   const jText=it.job.status==='done'?`Đã xuất ${it.job.files.length} MP4`:it.job.status==='running'?`Đang dựng ${it.job.progress}%`:it.job.status==='queued'?'Chờ dựng':'Lỗi dựng';
   right.append(node('span','badge '+it.job.status,jText));
  }
  if(it.project_id){
   const openBtn=node('button','link-button','Mở');
   openBtn.type='button';
   openBtn.addEventListener('click',()=>openProjectById(it.project_id).catch(e=>notice(e.message,true)));
   right.append(openBtn);
  }
  top.append(label,right);
  li.append(top);
  if(it.name)li.append(node('span','batch-item-url',it.url));
  if(it.message)li.append(node('span','help',it.message));
  ul.append(li);
 }
 box.append(ul);
 wrap.append(box);
}

async function pollBatch(){
 if(!activeBatch)return;
 try{
  const batch=await(await api('/api/batch-crawl/'+activeBatch)).json();
  drawBatchStatus(batch);
  await loadProjects();
  const anyRenderRunning=(batch.items||[]).some(it=>it.job&&['queued','running'].includes(it.job.status));
  if(!['queued','running'].includes(batch.status)&&!anyRenderRunning){
   activeBatch=null;
   notice(batch.message||'Đã hoàn tất lô crawl & render.',batch.status==='failed');
   loadJobs().catch(()=>{});
   return;
  }
 }catch{
  activeBatch=null;
  return;
 }
 setTimeout(pollBatch,2000);
}

$('start-batch').addEventListener('click',()=>busy($('start-batch'),async()=>{
 const urls=parseBatchTextarea();
 if(!urls.length)throw Error('Chọn file .txt hoặc dán ít nhất 1 URL vào ô danh sách.');
 sync();
 if($('batch-auto-render').checked)validateVoiceFields();
 const batchOptions={
  ...project.options,
  split_mode:$('batch-split-mode').value,
  comments_per_video:Number($('batch-comments-per-video').value)||10,
  video_count:Number($('batch-video-count').value)||3,
 };
 const limit=Number($('batch-limit').value)||30;
 const auto_render=$('batch-auto-render').checked;
 const batch=await json('/api/batch-crawl',{urls,limit,auto_render,options:batchOptions});
 activeBatch=batch.id;
 drawBatchStatus(batch);
 notice(`Đã bắt đầu crawl ${batch.total} URL${auto_render?' kèm tự động render':''}.`);
 pollBatch();
}));

function startCrawlProgress(){
 let stopped=false;
 const timer=setInterval(async()=>{
  try{
   const state=await(await api('/api/crawl-status')).json();
   if(stopped||state.status!=='running')return;
   const elapsed=Math.round((Date.now()/1000-state.started));
   $('crawl-note').textContent=`Đã đọc ${state.seen||0} bình luận · giữ ${Math.min(state.captured||0,state.limit)}/${state.limit} ảnh · ${state.failed||0} lỗi chụp · ${elapsed} giây. Đang tiếp tục tìm bình luận nhiều tim hơn…`;
  }catch{}
 },1500);
 return()=>{stopped=true;clearInterval(timer);};
}
$('crawl-form').addEventListener('submit',e=>{e.preventDefault();busy($('crawl'),async()=>{
 $('crawl').textContent='Đang chụp bình luận…';
 $('crawl-note').textContent='Đang mở nguồn và chụp bình luận. Nguồn lớn có thể cần tới 10 phút.';
 const stopProgress=startCrawlProgress();
 try{
  sync();await json('/api/projects',project);
  const result=await json('/api/crawl',{url:$('source-url').value,limit:Number($('crawl-limit').value),project_id:project.id});
  sync();
  if(result.name)project.name=result.name;
  else if(!project.name||project.name==='Video chưa đặt tên')project.name=result.suggested_name||'Video chưa đặt tên';
  project.url=result.url;project.post=result.post||'';project.author=result.author||'';project.post_image=result.post_image||'';project.post_captured_at=result.post_captured_at||'';project.post_capture_error=result.post_capture_error||'';
  project.crawled_at=result.crawled_at||'';project.crawl_date=result.crawl_date||'';
  project.comments=result.comments.map(commentDefaults);project.crawl_note=result.crawl_note;
  await json('/api/projects',project);await Promise.all([loadAssets(),loadProjects()]);fill();dirty=false;
  notice(!project.post_image?`Đã chụp ${result.comments.length} bình luận nhưng chưa có ảnh bài gốc. Xem lỗi ở phần Mở đầu; không dựng thẻ chữ thay thế.`:result.comments.length?`Đã chụp bài gốc và ${result.comments.length} ảnh bình luận thật.`:'Đã chụp bài gốc, chưa có bình luận. Thử đăng nhập nguồn.',!project.post_image||!result.comments.length);
 }catch(e){$('crawl-note').textContent=e.message;throw e;}
 finally{stopProgress();}
});});

for(const [id,platform] of [['login-tiktok','tiktok'],['login-threads','threads'],['login-tiktok-batch','tiktok'],['login-threads-batch','threads']]){
 $(id).addEventListener('click',()=>busy($(id),async()=>{const r=await json('/api/login/'+platform,{});notice(r.message);}));
}
function appendComments(rows){if(!Array.isArray(rows)||!rows.every(c=>typeof c.text==='string'))throw Error('JSON phải có comments là danh sách với trường text.');if(project.comments.length+rows.length>120)throw Error('Mỗi dự án tối đa 120 bình luận.');project.comments.push(...rows.map(c=>commentDefaults({...c,author:String(c.author||'Người dùng'),text:c.text,likes:Math.max(0,Number(c.likes)||0)})));drawComments();touch();}
$('import-text').addEventListener('click',()=>{try{const rows=$('manual-input').value.split('\n').filter(s=>s.trim()).map(s=>{const i=s.indexOf('|');return i<0?{text:s.trim()}:{author:s.slice(0,i).trim(),text:s.slice(i+1).trim()};});appendComments(rows);$('manual-input').value='';notice(`Đã thêm ${rows.length} bình luận.`);}catch(e){notice(e.message,true);}});
$('import-json').addEventListener('change',async()=>{try{const file=$('import-json').files[0];if(!file)return;if(file.size>2_000_000)throw Error('JSON vượt 2MB');const value=JSON.parse(await file.text());if(value.options&&Array.isArray(value.comments)){if(dirty){sync();await json('/api/projects',project);}const candidate={...freshProject(),...value,id:newId(),comments:value.comments.map(commentDefaults),options:{...freshProject().options,...value.options}};await json('/api/projects',candidate);project=candidate;await loadAssets();fill();await loadProjects();}else appendComments(Array.isArray(value)?value:value.comments);notice('Đã nhập JSON.');}catch(e){notice(e.message,true);}finally{$('import-json').value='';}});
$('export-json').addEventListener('click',()=>{sync();const url=URL.createObjectURL(new Blob([JSON.stringify(project,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='commentcut-project.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('load-demo').addEventListener('click',()=>{if(dirty){sync();json('/api/projects',project).catch(e=>notice(e.message,true));}project=freshProject();project.name='Chuyện đi làm · kịch bản minh họa';project.author='CommentCut · nội dung minh họa';project.post='Đi làm vui nhất là lúc nào?';project.comments=[commentDefaults({author:'Minh',text:'Lúc đồng nghiệp bảo: hôm nay sếp nghỉ! ',likes:128}),commentDefaults({author:'An',text:'Lúc nhận lương. Nhưng niềm vui thường kéo dài đúng năm phút.',likes:96}),commentDefaults({author:'Linh',text:'Lúc tan làm mà trời không mưa. Hạnh phúc đơn giản vậy thôi.',likes:73})];project.options.default_sound=library.find(a=>a.kind==='sound')?.id||'';project.options.default_meme=library.find(a=>a.kind==='image')?.id||'';fill();touch();notice('Đã nạp kịch bản minh họa tự viết.');});
$('upload-assets').addEventListener('click',()=>busy($('upload-assets'),async()=>{const files=Array.from($('asset-files').files);if(!files.length)throw Error('Chọn ít nhất một tệp.');for(let i=0;i<files.length;i++){const form=new FormData();form.append('file',files[i]);$('upload-assets').textContent=`Đang nạp ${i+1}/${files.length}…`;await api('/api/assets/'+$('asset-kind').value,{method:'POST',body:form});}await loadAssets();$('asset-files').value='';notice(`Đã thêm ${files.length} tệp.`);}));
$('create-demo-assets').addEventListener('click',()=>busy($('create-demo-assets'),async()=>{$('create-demo-assets').textContent='Đang tạo media…';await json('/api/demo-assets',{});await loadAssets();notice('Đã tạo nền chuyển động, meme chữ và hiệu ứng âm thanh gốc.');}));
async function previewVoice(button,index=0,provider=project.options.provider){return busy(button,async()=>{sync();button.textContent='Đang tạo giọng…';const r=await api('/api/voice-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({options:{...project.options,provider},voice_index:index})});if(voiceUrl)URL.revokeObjectURL(voiceUrl);voiceUrl=URL.createObjectURL(await r.blob());$('voice-player').src=voiceUrl;$('voice-player').hidden=false;$('voice-player').play().catch(()=>{});});}
$('voice-preview').addEventListener('click',()=>previewVoice($('voice-preview')));
function drawVoiceFields(voices){
 const fields=$('eleven-voice-fields');
 $('eleven-voice-count').value=voices.length;
 fields.replaceChildren();
 voices.forEach((value,index)=>{
  const id='eleven-voice-'+(index+1);
  const label=node('label','',`Voice ID ${index+1}`);label.htmlFor=id;
  const input=node('input');input.id=id;input.maxLength=100;input.autocomplete='off';input.value=value;
  const button=node('button','quiet',`Nghe giọng ${index+1}`);button.type='button';
  button.addEventListener('click',()=>previewVoice(button,index,'elevenlabs'));
  fields.append(label,input,button);
 });
}
function validateVoiceFields(){
 const count=$('eleven-voice-count');
 if(!count.checkValidity()||!count.value)throw Error('Nhập số giọng ElevenLabs từ 1 đến 120.');
 const voices=project.options.elevenlabs_voices;
 if(voices.length!==Number(count.value)||voices.length>1&&!voices.every(Boolean)){
  throw Error(`Nhập đủ ${count.value} Voice ID ElevenLabs.`);
 }
}
$('eleven-voice-count').addEventListener('change',()=>{
 const count=$('eleven-voice-count');
 if(!count.value||!count.reportValidity())return;
 const voices=sync().options.elevenlabs_voices;
 drawVoiceFields(Array.from({length:Number(count.value)},(_,i)=>voices[i]??''));
 sync();touch();
});
$('eleven-voice-fields').addEventListener('input',()=>{sync();touch();});
for(const id of ['use-meme-image','use-meme-sound'])$(id).addEventListener('click',()=>{const button=$(id);const enabled=button.getAttribute('aria-pressed')!=='true';button.setAttribute('aria-pressed',String(enabled));button.textContent=button.dataset.label+': '+(enabled?'Bật':'Tắt');sync();touch();});


async function loadSettings(){const cfg=await(await api('/api/settings')).json();for(const[k,v]of Object.entries(cfg))if(!['elevenlabs_key','vbee_token'].includes(k)&&$(k))$(k).value=v;$('eleven-status').textContent=cfg.elevenlabs_key?'· đã lưu key':'';$('vbee-status').textContent=cfg.vbee_token?'· đã lưu token':'';}
$('settings-form').addEventListener('submit',e=>{e.preventDefault();const button=e.submitter;busy(button,async()=>{const values={};for(const id of ['elevenlabs_key','elevenlabs_voice','elevenlabs_model','vbee_token','vbee_app_id','vbee_voice','vbee_callback'])values[id]=$(id).value;await json('/api/settings',values);$('elevenlabs_key').value='';$('vbee_token').value='';await loadSettings();notice('Đã lưu cấu hình. Chọn giọng và nghe thử ở trang Biên tập.');});});
function jobBlock(job,compact=false){const wrap=node('div',compact?'job-progress':'export-job');if(!compact)wrap.append(node('h2','',job.name));wrap.append(node('p','',`${{queued:'Đang chờ',running:'Đang dựng',done:'Hoàn tất',failed:'Lỗi',cancelled:'Đã hủy',interrupted:'Bị gián đoạn'}[job.status]} · ${job.message}`));if(['queued','running'].includes(job.status)){const progress=node('progress');progress.max=100;progress.value=job.progress;progress.setAttribute('aria-label','Tiến độ dựng video');const cancel=node('button','quiet','Hủy dựng');cancel.addEventListener('click',()=>busy(cancel,async()=>{await json(`/api/jobs/${job.id}/cancel`,{});notice('Đã yêu cầu hủy.');}));wrap.append(progress,cancel);}if(job.files?.some(file=>file.endsWith('.mp4'))){const links=node('div','download-links');for(const file of job.files){const a=node('a','',file);a.href=`/api/jobs/${job.id}/files/${encodeURIComponent(file)}`;a.download=file;links.append(a);}wrap.append(links);if(!compact){const file=job.files.find(f=>f.endsWith('.mp4'));if(file){const v=node('video');v.src=`/api/jobs/${job.id}/files/${encodeURIComponent(file)}`;v.controls=true;v.preload='metadata';wrap.append(v);}}}return wrap;}
async function loadJobs(){const jobs=await(await api('/api/jobs')).json();$('jobs').replaceChildren();if(!jobs.length)$('jobs').append(node('p','help','Chưa có bản dựng. Tạo kịch bản và bấm Dựng video để bắt đầu.'));jobs.forEach(j=>$('jobs').append(jobBlock(j)));if(!activeJob){const pending=jobs.find(j=>['queued','running'].includes(j.status));if(pending){activeJob=pending.id;pollJob();}}}
$('refresh-jobs').addEventListener('click',()=>busy($('refresh-jobs'),loadJobs));
$('refresh-days').addEventListener('click',()=>busy($('refresh-days'),loadCrawlDays));
$('render').addEventListener('click',()=>busy($('render'),async()=>{validate();const job=await json('/api/jobs',project);dirty=false;activeJob=job.id;$('active-job').replaceChildren(jobBlock(job,true));await loadProjects();notice('Đã gửi toàn bộ kịch bản vào hàng đợi dựng.');pollJob();}));
async function pollJob(){if(!activeJob)return;try{const job=await(await api('/api/jobs/'+activeJob)).json();$('active-job').replaceChildren(jobBlock(job,true));if(!['queued','running'].includes(job.status)){activeJob=null;if(job.status==='done')notice('Video đã sẵn sàng. Tải MP4 bên dưới hoặc mở Video đã dựng.');else notice(job.message,job.status==='failed');loadJobs().catch(()=>{});loadCrawlDays().catch(()=>{});return;}}catch(e){notice('Mất kết nối khi kiểm tra tác vụ. Tác vụ vẫn có thể đang chạy; mở Video đã dựng để kiểm tra.',true);activeJob=null;return;}setTimeout(pollJob,1500);}
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
async function init(){
 try{
  const health=await(await api('/api/health')).json();
  $('health').textContent=health.ffmpeg?'FFmpeg sẵn sàng':'Cần cài FFmpeg';
  if(!health.ffmpeg)notice('Chưa tìm thấy FFmpeg. Xem README để cài trước khi dựng.',true);
  await Promise.all([loadAssets(),loadProjects(),loadSettings()]);
  fill();updateBatchControls();await loadJobs();
  const batches=await(await api('/api/batch-crawl')).json();
  const runningBatch=batches.find(b=>['queued','running'].includes(b.status));
  if(runningBatch){setCrawlTab('batch');activeBatch=runningBatch.id;drawBatchStatus(runningBatch);pollBatch();}
  else if(batches.length){drawBatchStatus(batches[0]);}
 }catch(e){$('health').textContent='Mất kết nối';notice(e.message,true);}
}
init();
