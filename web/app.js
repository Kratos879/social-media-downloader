const $=id=>document.getElementById(id), input=$('url-input');
const defaults='粘贴后只加载预览，点击图片才保存原文件。';
let token='',jobs=[],photos=[],lastPhotos='',lastQueue='',view='preview',viewChosen=false;
let submitting=false,selecting=false,exporting=false,disconnected=false,previewKey=null;
let inputTimer,pollTimer,toastTimer,intent=null,queueWasActive=null;const pendingTexts=[],selected=new Set();
const symbols={
 instagram:'<img src="/assets/instagram.svg" alt="">',
 twitter:'<img src="/assets/x.svg" alt="">',
 check:'<svg viewBox="0 0 18 18" fill="none"><path d="m4 9 3 3 7-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
 zoom:'<svg viewBox="0 0 20 20" fill="none"><circle cx="8.5" cy="8.5" r="5.2" stroke="currentColor" stroke-width="1.6"/><path d="m12.5 12.5 4.2 4.2M8.5 6v5m-2.5-2.5h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
 download:'<svg viewBox="0 0 20 20" fill="none"><path d="M10 3v9m-3-3 3 3 3-3M4 13v4h12v-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
};
function element(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e;}
function bytes(n){return n>=1048576?`${(n/1048576).toFixed(1)} MB`:`${Math.round(n/1024)} KB`;}
const platformNames={instagram:'Instagram',twitter:'X / Twitter',xiaohongshu:'小红书',douyin:'抖音',tiktok:'TikTok',bilibili:'哔哩哔哩',youtube:'YouTube',weibo:'微博',pinterest:'Pinterest'};
for(const p of Object.keys(platformNames))if(!symbols[p])symbols[p]=`<img src="/assets/${p}.svg" alt="">`;
function platformName(p){return platformNames[p]||p;}
function duration(n){if(!n)return '';return `${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`;}
function toast(text){$('toast').textContent=text;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),3500);}
function message(text,state=''){$('input-message').textContent=text;$('input-message').className=`input-message ${state}`;}
async function api(path,body){const r=await fetch(path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify(body)});const result=await r.json();if(!r.ok)throw new Error(result.error||'操作失败，请重试。');return result;}
function action(text,onClick,cls='text-button'){const b=element('button',cls,text);b.addEventListener('click',async()=>{b.disabled=true;try{await onClick();}catch(e){toast(e.message);}finally{b.disabled=false;}});return b;}
function photoId(p){return `photo-${p.jobId}-${p.index}`;}
function chosenPhotos(){return photos.filter(p=>selected.has(p.key));}
function latestJobs(){const latest=new Map();jobs.forEach(j=>{if(j.mode==='selective')latest.set(`${j.platform}:${j.key}`,j);});return [...latest.values()];}
async function submit(text=input.value){
 clearTimeout(inputTimer);if(!text.trim())return;if(submitting){pendingTexts.push(text);return;}
 submitting=true;$('paste-button').disabled=true;
 try{
  if(!token)await refresh();const result=await api('/api/jobs',{text});
  if(input.value.trim()===text.trim())input.value='';view='preview';viewChosen=true;selected.clear();
  const n=result.jobs.filter(j=>!j.duplicate).length;
  intent={type:'parse',ids:result.jobs.map(j=>j.id)};
  message(n?`已添加 ${n} 条链接，正在解析预览，尚未保存原文件。`:'已打开这条链接的解析结果，点选后保存。','success');
  await refresh(true);schedulePoll();
  if(result.jobs.length){const row=document.getElementById(`queue-${result.jobs[0].id}`);row?.scrollIntoView({behavior:'smooth',block:'nearest'});}
 }catch(e){message(e.message,'error');}finally{submitting=false;$('paste-button').disabled=false;if(pendingTexts.length)submit(pendingTexts.shift());else if(input.value.trim()&&input.value.trim()!==text.trim())inputTimer=setTimeout(()=>submit(),600);}
}
function syncSelection(){
 $('photo-grid').classList.toggle('selecting',selecting);$('toggle-selection').querySelector('span').textContent=selecting?'取消':'批量选择';
 $('toggle-selection').disabled=!photos.length;$('selection-count').hidden=!selecting;$('selection-count').textContent=`已选 ${selected.size} 项`;
 $('select-all').hidden=!selecting;$('select-all').textContent=selected.size===photos.length&&photos.length?'取消全选':'全选';
 const chosen=chosenPhotos(),unsaved=chosen.filter(p=>!p.file.saved&&!['queued','downloading'].includes(p.file.status));
 $('download-selected').hidden=!selecting||view==='saved';$('download-selected').disabled=!unsaved.length;$('download-selected').textContent=`保存所选${unsaved.length?` (${unsaved.length})`:''}`;
 $('export-selected').hidden=!selecting||view!=='saved';$('export-selected').disabled=!chosen.length||chosen.some(p=>!p.file.saved)||exporting;
 $('export-selected').textContent=exporting?'正在打包…':`打包所选${chosen.length?` (${chosen.length})`:''}`;
 document.querySelectorAll('.photo').forEach(card=>{const checked=selected.has(card.dataset.key);card.classList.toggle('selected',checked);const b=card.querySelector('.photo-select');b.setAttribute('aria-checked',String(checked));b.setAttribute('aria-label',`${checked?'取消选择':'选择'}图片 ${card.dataset.position}`);});
}
function togglePhoto(key){selecting=true;if(selected.has(key))selected.delete(key);else selected.add(key);syncSelection();}
async function savePhotos(chosen){
 const items=chosen.filter(p=>!p.file.saved).map(p=>({id:p.jobId,index:p.index}));
 if(!items.length){toast('这些原文件已保存');return;}
 try{const result=await api('/api/download',{items});intent={type:'save',items};message(result.queued?`仅保存所选 ${result.queued} 项，其余内容只保留预览。`:'所选内容已保存或正在保存。','success');toast(result.queued?`仅将所选 ${result.queued} 项加入保存队列`:'所选内容已保存或正在保存');await refresh(true);schedulePoll();}catch(e){toast(e.message);}
}
function renderPhoto(p,position){
 const f=p.file,card=element('article',`photo ${f.saved?'saved':''} ${f.preview_ready?'':'without-preview'}`);card.id=photoId(p);card.dataset.key=p.key;card.dataset.position=String(position+1);card.dataset.order=String(f.order||p.index+1);card.dataset.ratio=String((f.height||1)/(f.width||1));
 const open=element('button','photo-open');open.setAttribute('aria-label',f.saved?`查看已保存图片 ${position+1}`:`保存图片 ${position+1}`);
 if(f.preview_ready){const img=element('img');img.src=`/thumbs/${p.jobId}/${p.index}`;img.alt=`${platformName(p.platform)} 第 ${f.order||p.index+1} 项`;img.loading='lazy';img.decoding='async';open.append(img);}
 else{const placeholder=element('span','photo-placeholder');placeholder.append(element('span','',String(f.order||p.index+1)),element('small','',p.jobStatus==='parsing'?'等待预览':'请重新解析预览'));open.append(placeholder);open.disabled=!f.saved;}
 open.addEventListener('click',()=>selecting?togglePhoto(p.key):f.saved?showPreview(p.key):savePhotos([p]));
 const check=element('button','photo-select');check.innerHTML=symbols.check;check.setAttribute('role','checkbox');check.setAttribute('aria-checked','false');check.addEventListener('click',()=>togglePhoto(p.key));
 const source=element('a',`platform-badge ${p.platform}`);source.innerHTML=symbols[p.platform];source.href=p.url;source.target='_blank';source.rel='noopener noreferrer';source.title=`查看 ${platformName(p.platform)} 原帖`;source.setAttribute('aria-label',source.title);
 const ordinal=element('span','photo-number',`${f.order||p.index+1}/${p.total}`);
 const zoom=element('button','photo-zoom');zoom.innerHTML=symbols.zoom;zoom.title='只查看预览，不保存原文件';zoom.setAttribute('aria-label',`预览图片 ${position+1}`);zoom.disabled=!f.preview_ready&&!f.saved;zoom.addEventListener('click',()=>showPreview(p.key));
 if(f.kind==='video'){card.classList.add('video-card');const meta=element('span','video-meta',`▶ ${duration(f.duration)}${f.quality?' · '+f.quality:''}`);card.append(meta);open.setAttribute('aria-label',f.saved?`播放已保存视频 ${position+1}`:`保存视频 ${position+1}`);}
 const status=element('span',`photo-status ${f.saved?'is-saved':''}`,f.saved?'✓ 已保存':['queued','downloading'].includes(f.status)?'保存中…':f.status==='error'?'保存失败，可重试':'点击保存');
 if(f.error)status.title=f.error;
 card.append(open,element('div','photo-shade'),check,source,ordinal,zoom,status);
 return card;
}
function layoutMasonry(){
 const grid=$('photo-grid'),width=grid.clientWidth;if(!width)return;
 const gap=width<600?10:14,minWidth=width<600?145:215,columns=Math.max(1,Math.floor((width+gap)/(minWidth+gap))),columnWidth=(width-gap*(columns-1))/columns,heights=Array(columns).fill(0);
 // Iterate in source order; always place the next image at the next lowest position.
 for(const card of grid.children){let column=0;for(let i=1;i<columns;i++)if(heights[i]<heights[column]-1)column=i;
  const height=columnWidth*Number(card.dataset.ratio||1);card.style.width=`${columnWidth}px`;card.style.height=`${height}px`;card.style.left=`${column*(columnWidth+gap)}px`;card.style.top=`${heights[column]}px`;heights[column]+=height+gap;
 }
 grid.style.height=`${Math.max(0,...heights)- (grid.children.length?gap:0)}px`;
}
function renderQueue(){
 const tasks=latestJobs().filter(j=>view==='preview'||['queued','parsing','downloading','failed'].includes(j.status)).reverse();
 const data=JSON.stringify(tasks);if(data===lastQueue)return;lastQueue=data;
 $('queue-panel').hidden=!tasks.length;const active=tasks.filter(j=>['queued','parsing','downloading'].includes(j.status)).length;
 const previewTotal=tasks.reduce((n,j)=>n+(j.preview_count||0),0),savedTotal=tasks.reduce((n,j)=>n+(j.saved_count||0),0),parseTotal=tasks.reduce((n,j)=>n+(j.parse_seconds||0),0);
 $('queue-summary').textContent=active?`${active} 条进行中 · 已显示 ${previewTotal} 项预览`:`${previewTotal} 项预览 · 已保存 ${savedTotal} 项 · 解析共 ${parseTotal.toFixed(1)} 秒`;
 $('retry-failed').hidden=!tasks.some(j=>j.status==='failed');
 if(active)$('queue-panel').open=true;else if(queueWasActive!==false)$('queue-panel').open=false;
 queueWasActive=!!active;
 $('queue-list').replaceChildren(...tasks.map(job=>{
  const row=element('div',`queue-item ${job.status}`);row.id=`queue-${job.id}`;
  const icon=element('span','queue-icon');icon.innerHTML=symbols[job.platform];icon.title=platformName(job.platform);
  const copy=element('div','queue-copy');const total=job.expected,ready=job.preview_count||0,saved=job.saved_count||0;
  let text=job.status==='parsing'?total===null?'正在获取媒体清单':`预览 ${ready}/${total} 项`:job.status==='downloading'?`本次保存 ${job.download_done||0}/${job.download_requested||0} 项`:
   job.status==='ready'?(total===0?job.message:`预览 ${ready}/${total} · 已保存 ${saved}/${total}`):job.message;
  copy.append(element('p','',text));
  let detail=job.status==='queued'?'等待前面的解析任务完成':job.parse_seconds!==null&&job.parse_seconds!==undefined?`解析用时 ${job.parse_seconds.toFixed(1)} 秒`:`已用 ${Number(job.elapsed||0).toFixed(1)} 秒`;
  if(job.status==='ready')detail+=job.download_errors?` · ${job.download_errors} 项保存失败：${job.files.find(f=>f.error)?.error||'可重试'}`:' · 未点选的原文件不会保存';
  if(job.status==='downloading'){
   const current=job.files[job.current_index];if(current)detail=`${current.phase||'正在保存'} · 第 ${job.current_index+1} 项：${bytes(current.downloaded_bytes||0)}${current.total_bytes?` / ${bytes(current.total_bytes)}`:''}`;
  }
  copy.append(element('small','',detail));
  const progress=element('progress','task-progress');
  progress.max=job.status==='downloading'?Math.max(1,job.download_requested||1):Math.max(1,total||1);
  if(total!==null)progress.value=job.status==='downloading'?(job.download_done||0):ready;
  progress.setAttribute('aria-label',job.status==='downloading'?text:`预览加载 ${ready}/${total||'未知'}`);copy.append(progress);
  if(total){const steps=element('div','progress-steps');job.files.forEach((f,i)=>{const step=element('span',`progress-step ${f.saved?'saved':f.preview_ready?'ready':''} ${f.status==='downloading'?'working':''}`,String(i+1));step.title=`第 ${i+1} 项：${f.saved?'已保存':f.preview_ready?'预览就绪，未保存':'预览加载中'}`;steps.append(step);});copy.append(steps);}
  row.append(icon,copy);
  if(['parsing','downloading'].includes(job.status))row.append(element('i','spinner'));
  else row.append(action('重新解析',async()=>{const result=await api('/api/retry',{id:job.id});view='preview';viewChosen=true;await refresh(true);schedulePoll();toast('只重新解析预览，不自动保存原文件');}));
  return row;
 }));
}
function showPreview(key){
 const p=photos.find(p=>p.key===key);if(!p)return;previewKey=key;const position=photos.indexOf(p),f=p.file;
 const isVideo=f.kind==='video'&&f.saved,video=$('preview-video'),image=$('preview-image');
 const src=isVideo?`/files/${p.jobId}/${p.index}`:f.saved?`/files/${p.jobId}/${p.index}`:`/thumbs/${p.jobId}/${p.index}`;
 image.hidden=isVideo;video.hidden=!isVideo;
 if(isVideo){if(video.dataset.key!==p.key){video.src=src;video.dataset.key=p.key;video.load();}image.removeAttribute('src');}
 else{if(video.hasAttribute('src')){video.pause();video.removeAttribute('src');video.dataset.key='';video.load();}if(image.getAttribute('src')!==src)image.src=src;}
 image.alt=`${platformName(p.platform)} 第 ${f.order||p.index+1} 项`;
 $('image-title').textContent=f.saved?(isVideo?'已保存的视频':'已保存的原文件'):(f.kind==='video'?'视频封面 · 尚未下载视频':'预览图 · 尚未保存原文件');$('image-position').textContent=`${position+1}/${photos.length}`;
 $('preview-info').textContent=`${f.width} × ${f.height}${f.kind==='video'?' · '+duration(f.duration):''}${f.saved?` · ${bytes(f.bytes)}`:' · 点保存后才获取原文件'}`;
 $('preview-platform').innerHTML=symbols[p.platform];$('preview-original').href=p.url;
 $('preview-save').hidden=!!f.saved;$('preview-save').disabled=['queued','downloading'].includes(f.status);$('preview-save').textContent=$('preview-save').disabled?'保存中…':'保存原文件';
 $('preview-folder').hidden=!f.saved;$('previous-image').disabled=position===0;$('next-image').disabled=position===photos.length-1;
 if(!$('image-dialog').open)$('image-dialog').showModal();
}
async function exportSelected(){
 const chosen=chosenPhotos();if(!chosen.length||chosen.some(p=>!p.file.saved)||exporting)return;exporting=true;syncSelection();
 try{const r=await fetch('/api/archive',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Token':token},body:JSON.stringify({items:chosen.map(p=>({id:p.jobId,index:p.index}))})});
  if(!r.ok){const e=await r.json();throw new Error(e.error||'打包失败');}
  const url=URL.createObjectURL(await r.blob()),a=element('a');a.href=url;a.download=`images-${new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',dateStyle:'short',timeStyle:'medium'}).format(new Date()).replace(/[ :]/g,'-')}.zip`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);toast(`已打包 ${chosen.length} 项已保存原文件`);
 }catch(e){toast(e.message);}finally{exporting=false;syncSelection();}
}
async function refresh(force=false){
 try{
  const state=await api('/api/state');token=state.token;jobs=state.jobs;
  if(!$('supported-platforms').children.length){for(const p of state.platforms||[]){const b=element('button',`platform-chip ${p.state}`);b.innerHTML=symbols[p.id];b.append(document.createTextNode(({twitter:'X',bilibili:'B站'})[p.id]||p.name));b.title=p.detail;b.addEventListener('click',()=>{toast(`${p.name}：${p.detail}`);});$('supported-platforms').append(b);}}
  $('connection').className='connection';$('connection').replaceChildren(element('i'),document.createTextNode('本地运行'));
  if(disconnected){message(defaults);disconnected=false;}
  if(!viewChosen){view=latestJobs().length?'preview':'saved';}
  const sources=view==='preview'?latestJobs():jobs;
  const next=[...sources].reverse().flatMap(j=>j.files.map((file,index)=>({key:`${j.id}:${index}`,jobId:j.id,index,file,platform:j.platform,url:j.url,total:j.files.length,jobStatus:j.status}))).filter(p=>view!=='saved'||p.file.saved);
  const data=JSON.stringify(next);
  if(data!==lastPhotos||force){photos=next;lastPhotos=data;const valid=new Set(photos.map(p=>p.key));for(const key of selected)if(!valid.has(key))selected.delete(key);
   const scroll=$('library-scroll').scrollTop;$('photo-grid').replaceChildren(...photos.map(renderPhoto));layoutMasonry();$('library-scroll').scrollTop=scroll;syncSelection();
   if($('image-dialog').open){if(photos.some(p=>p.key===previewKey))showPreview(previewKey);else $('image-dialog').close();}
  }
  $('view-preview').classList.toggle('active',view==='preview');$('view-saved').classList.toggle('active',view==='saved');
  $('history-count').textContent=`${photos.length} 项`;$('empty-state').hidden=!!photos.length;$('end-note').hidden=!photos.length;
  $('empty-state').querySelector('h3').textContent=view==='preview'?'先粘贴链接，解析图片预览':'还没有保存的图片';
  $('empty-state').querySelector('p').textContent='原文件只有在你点选后才会保存。';
  const saved=jobs.reduce((n,j)=>n+j.files.filter(f=>f.saved).length,0),storage=state.storage||{};
  $('saved-label').textContent=`已保存 ${saved} 项原文件 · ${bytes(storage.saved_bytes||0)}`;
  $('cache-size').textContent=`预览缓存 ${bytes(storage.preview_bytes||0)}`;$('clear-cache').disabled=!storage.preview_bytes;
  $('folder-path').textContent=state.folder;$('folder-path').title=state.folder;
  renderQueue();
  if(intent?.type==='parse'){
   const batch=jobs.filter(j=>intent.ids.includes(j.id));
   if(batch.length===intent.ids.length&&batch.every(j=>['ready','failed'].includes(j.status))){const total=batch.reduce((n,j)=>n+j.files.length,0);const failed=batch.filter(j=>j.status==='failed').length;message(failed?`已解析 ${total} 项；${failed} 条未完成，展开任务可查看原因。`:`解析完成，共 ${total} 项可选。点选后才保存原文件。`,failed?'error':'success');intent=null;}
  }else if(intent?.type==='save'){
   const chosen=intent.items.map(item=>jobs.find(j=>j.id===item.id)?.files[item.index]).filter(Boolean);
   if(chosen.length===intent.items.length&&chosen.every(f=>f.saved||f.status==='error')){const count=chosen.filter(f=>f.saved).length;message(`本次已保存 ${count}/${chosen.length} 项，未选中的图片只保留预览。`,count===chosen.length?'success':'error');intent=null;}
  }
 }catch(e){disconnected=true;$('connection').className='connection offline';$('connection').replaceChildren(element('i'),document.createTextNode('连接已断开'));message('本地服务未连接，请双击“启动图片下载.command”后刷新。','error');throw e;}
}
function schedulePoll(){clearTimeout(pollTimer);const active=jobs.some(j=>['queued','parsing','downloading'].includes(j.status)||j.files.some(f=>f.status==='queued'));pollTimer=setTimeout(async()=>{try{await refresh();}catch(_){}schedulePoll();},document.hidden?10000:active?300:2500);}
input.addEventListener('paste',e=>{const text=e.clipboardData?.getData('text/plain');if(!text)return;e.preventDefault();input.value=text;submit(text);});
input.addEventListener('input',()=>{clearTimeout(inputTimer);if(/https?:\/\//i.test(input.value))inputTimer=setTimeout(()=>submit(),1000);});
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit();}});
$('paste-button').addEventListener('click',async()=>{try{const text=await navigator.clipboard.readText();if(!text.trim()){toast('剪贴板里还没有链接');input.focus();return;}input.value=text;await submit(text);}catch(_){input.focus();toast('请在输入框内按粘贴快捷键');}});
$('toggle-selection').addEventListener('click',()=>{selecting=!selecting;if(!selecting)selected.clear();syncSelection();});
$('select-all').addEventListener('click',()=>{if(selected.size===photos.length)selected.clear();else photos.forEach(p=>selected.add(p.key));syncSelection();});
$('download-selected').addEventListener('click',()=>savePhotos(chosenPhotos()));$('export-selected').addEventListener('click',exportSelected);
for(const name of ['preview','saved'])$(`view-${name}`).addEventListener('click',()=>{view=name;viewChosen=true;selected.clear();selecting=false;lastQueue='';refresh(true).catch(()=>{});});
$('retry-failed').addEventListener('click',async()=>{try{for(const j of latestJobs().filter(j=>j.status==='failed'))await api('/api/retry',{id:j.id});await refresh(true);schedulePoll();}catch(e){toast(e.message);}});
$('clear-cache').addEventListener('click',async()=>{try{const result=await api('/api/cache/clear',{});await refresh(true);toast(`已清理 ${bytes(result.removed_bytes)} 预览缓存，已保存原文件不受影响`);}catch(e){toast(e.message);}});
$('open-folder').addEventListener('click',async()=>{try{await api('/api/open-folder',{});}catch(e){toast(e.message);}});
$('previous-image').addEventListener('click',()=>{const i=photos.findIndex(p=>p.key===previewKey);if(i>0)showPreview(photos[i-1].key);});
$('next-image').addEventListener('click',()=>{const i=photos.findIndex(p=>p.key===previewKey);if(i<photos.length-1)showPreview(photos[i+1].key);});
$('close-image').addEventListener('click',()=>$('image-dialog').close());$('image-dialog').addEventListener('close',()=>{previewKey=null;$('preview-image').removeAttribute('src');const v=$('preview-video');v.pause();v.removeAttribute('src');v.dataset.key='';v.load();});
$('preview-save').addEventListener('click',()=>{const p=photos.find(p=>p.key===previewKey);if(p)savePhotos([p]);});
$('preview-folder').addEventListener('click',async()=>{try{const p=photos.find(p=>p.key===previewKey);if(p)await api('/api/open-folder',{id:p.jobId});}catch(e){toast(e.message);}});
$('preview-retry').addEventListener('click',async()=>{try{const p=photos.find(p=>p.key===previewKey);if(p){await api('/api/retry',{id:p.jobId});$('image-dialog').close();view='preview';viewChosen=true;await refresh(true);schedulePoll();}}catch(e){toast(e.message);}});
document.addEventListener('keydown',e=>{if(!$('image-dialog').open)return;if(e.key==='ArrowLeft'){e.preventDefault();$('previous-image').click();}if(e.key==='ArrowRight'){e.preventDefault();$('next-image').click();}});
document.querySelectorAll('.help-trigger').forEach(b=>b.addEventListener('click',()=>$('help-dialog').showModal()));$('close-help').addEventListener('click',()=>$('help-dialog').close());
for(const id of ['help-dialog','image-dialog'])$(id).addEventListener('click',e=>{if(e.target!==$(id))return;const r=$(id).getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$(id).close();});
new ResizeObserver(layoutMasonry).observe($('photo-grid'));
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh().catch(()=>{});schedulePoll();});
if(!/Mac|iPhone|iPad/.test(navigator.platform))$('paste-shortcut').textContent='Ctrl V';
refresh().catch(()=>{}).finally(schedulePoll);
