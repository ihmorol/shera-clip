'use strict';
const $ = id => document.getElementById(id);
let endpoint = '', token = '', jobs = [], detail = null, selected = null, connected = false, busy = false;
const time = n => new Date(Math.max(0, Number(n || 0)) * 1000).toISOString().slice(11, 19);
const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(message) { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(path, options = {}) {
  if (!connected && path !== '/health') throw new Error('Connect the local companion first.');
  const headers = {'Authorization': `Bearer ${token}`, ...(options.headers || {})};
  if (options.body && !(options.body instanceof FormData)) { headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body); }
  const response = await fetch(endpoint + '/companion' + path, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.error || `Request failed (${response.status})`);
  return data;
}
async function perform(action) {
  if (busy) return;
  busy = true; notice('Working…');
  try { await action(); notice(''); } catch (error) { notice(error.message || 'Could not reach the companion. Check it is running and allow local network access in your browser.'); }
  finally { busy = false; }
}
function route() {
  const name = ['library','import','review','exports'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'library';
  for (const section of ['library','import','review','exports']) $(section).hidden = section !== name;
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('selected', a.hash === '#' + name));
  if (name === 'exports' && detail) perform(loadExports);
}
window.addEventListener('hashchange', route); route();
$('connection-button').onclick = () => { $('connection').hidden = !$('connection').hidden; };
$('connect-form').onsubmit = event => {
  event.preventDefault();
  perform(async () => {
    const address = new URL($('endpoint').value);
    if (address.protocol !== 'http:' || !['127.0.0.1','localhost'].includes(address.hostname) || address.username || address.password || address.search || address.hash || address.pathname !== '/') throw new Error('Use the companion’s loopback address, such as http://127.0.0.1:8765.');
    endpoint = address.origin; token = $('token').value.trim();
    const health = await api('/health'); connected = true;
    $('connect-status').textContent = 'Connected. Jobs and media are stored on this computer.';
    $('connection-button').textContent = 'Companion connected'; $('connection').hidden = true;
    if (health.setup && (!health.setup.ffmpeg || !health.setup.provider_key)) $('connect-status').textContent = 'Connected; finish FFmpeg and OpenRouter setup before processing.';
    await loadJobs();
  });
};
async function loadJobs() { jobs = (await api('/jobs')).jobs; renderJobs(); }
function renderJobs() {
  const query = $('job-search').value.toLowerCase(), filter = $('job-filter').value;
  const visible = jobs.filter(j => j.title.toLowerCase().includes(query) && (!filter || j.status === filter));
  $('jobs').innerHTML = visible.length ? '' : '<div class="empty panel">No videos match. Import a video or change the filters.</div>';
  for (const job of visible) {
    const button = document.createElement('button'); button.className = 'job-card';
    button.innerHTML = `<span class="badge">${escapeHtml(job.status)}</span><strong>${escapeHtml(job.title)}</strong><span class="time">${time(job.duration)} · ${escapeHtml(job.stage)}</span><small>${new Date(job.created * 1000).toLocaleDateString()} · ${escapeHtml(job.profile?.label || 'IELTS lesson')}</small>`;
    button.onclick = () => perform(() => openJob(job.id)); $('jobs').append(button);
  }
}
$('job-search').oninput = renderJobs; $('job-filter').onchange = renderJobs;
$('refresh').onclick = () => perform(loadJobs);
function profileFromForm() {
  const profile = {preset:$('preset').value, min_s:Number($('min-s').value),target_s:Number($('target-s').value),max_s:Number($('max-s').value)};
  profile.suggest_criteria = $('ai-criteria').checked;
  if ($('intent').value.trim()) profile.intent = $('intent').value.trim();
  if (!(5 <= profile.min_s && profile.min_s <= profile.target_s && profile.target_s <= profile.max_s && profile.max_s <= 600)) throw new Error('Choose durations between 5 and 600 seconds, with minimum ≤ target ≤ maximum.');
  return profile;
}
$('import-form').onsubmit = event => {
  event.preventDefault(); perform(async () => {
    const video = $('video').files[0], url = $('url').value.trim(), profile = profileFromForm();
  if (Boolean(video) === Boolean(url)) throw new Error('Choose one source: a video file or a direct video URL.');
    let result;
    if (video) {
      const form = new FormData(); form.append('video', video); form.append('profile', JSON.stringify(profile));
      for (const name of ['vtt','audio']) if ($(name).files[0]) form.append(name, $(name).files[0]);
      result = await api('/import', {method:'POST',body:form});
    } else {
      if ($('vtt').files.length || $('audio').files.length) throw new Error('Download this video first to import it with transcript or replacement audio.');
      result = await api('/import-url', {method:'POST',body:{url,profile}});
    }
    await loadJobs(); await openJob(result.job_id);
  });
};
async function openJob(id) {
  detail = await api('/jobs/' + encodeURIComponent(id)); selected = null; $('bench').hidden = true;
  $('job-intent').value = detail.job.profile?.intent || ''; $('job-profile').value = JSON.stringify(detail.job.profile || {preset:'ielts'},null,2);
  updateJob(); location.hash = 'review';
}
function updateJob() {
  const job = detail.job; $('job-title').textContent = job.title; $('job-state').textContent = job.status;
  $('job-controls').hidden = false; $('job-progress').textContent = `${job.stage} · ${Math.round((job.progress || 0)*100)}% · authorized up to $${Number(job.authorized_usd || 0).toFixed(2)}`;
  $('job-error').textContent = job.error || '';
  const locked = job.status === 'running' || detail.candidates.length > 0;
  $('save-criteria').disabled = locked; $('suggest-criteria').disabled = locked;
  $('authorize').disabled = job.status === 'running' || Boolean(job.authorized_usd) || job.stage === 'review';
  if (job.stage === 'criteria' && job.profile?.criteria_proposed && !job.profile.criteria_confirmed && $('job-profile').dataset.proposed !== job.id) { $('job-intent').value=job.profile.intent; $('job-profile').value=JSON.stringify(job.profile,null,2); $('job-profile').dataset.proposed=job.id; $('criteria-editor').open=true; }
  $('resume').disabled = !['paused','failed','waiting'].includes(job.status) || !job.authorized_usd;
  renderClips();
}
function filteredClips() {
  if (!detail) return [];
  const query = $('clip-search').value.toLowerCase(), filter = $('clip-filter').value;
  const reviews = new Map(detail.reviews.map(r => [r.candidate_id, r]));
  return detail.candidates.filter(c => {
    const status = reviews.get(c.id)?.status || 'pending';
    return (filter === 'all' || (filter === 'shortlisted' ? c.shortlisted : status === filter)) &&
      JSON.stringify([c.text,c.text_en,c.jev,reviews.get(c.id)?.title]).toLowerCase().includes(query);
  }).sort((a,b) => $('clip-sort').value === 'time' ? a.start-b.start : (b.score || 0)-(a.score || 0));
}
function renderClips() {
  const clips = filteredClips(); $('clips').innerHTML = clips.length ? '' : '<div class="panel empty">No matching moments. Processing may still be running, or this video may have no strong shortlist. Try “All candidates”.</div>';
  for (const clip of clips) {
    const button = document.createElement('button'); button.className = 'clip-card' + (selected?.candidate.id === clip.id ? ' active' : '');
    const review = detail.reviews.find(r => r.candidate_id === clip.id);
    button.innerHTML = `<span class="timecode">${time(clip.start)} — ${time(clip.end)}</span><strong>${escapeHtml(review?.title || clip.text_en?.slice(0,90) || clip.text?.slice(0,90) || 'Moment')}</strong><small>${escapeHtml(clip.category || 'Uncategorized')} · ${Math.round((clip.score || 0)*100)}/100 · ${escapeHtml(review?.status || 'pending')}</small>`;
    button.onclick = () => perform(() => openClip(clip.id)); $('clips').append(button);
  }
}
for (const id of ['clip-search','clip-filter','clip-sort']) $(id).addEventListener(id === 'clip-search' ? 'input' : 'change',renderClips);
async function ticket(path) { return endpoint + (await api('/media-ticket',{method:'POST',body:{path:path.replace(/^\/media\//,'/companion/media/')}})).url; }
async function openClip(id) {
  selected = await api(`/jobs/${detail.job.id}/clips/${id}`);
  const c = selected.candidate, r = selected.review;
  $('bench').hidden = false; $('clip-title').textContent = r.title || `Moment at ${time(r.start)}`;
  $('clip-start').value = r.start; $('clip-end').value = r.end; $('clip-heading').value = r.title || '';
  $('clip-captions').value = JSON.stringify(r.captions || [],null,2); $('clip-drafts').value = JSON.stringify(r.drafts || {},null,2);
  $('layout-mode').value = r.layout?.mode || 'full'; $('crop-box').value = (r.layout?.crop || [0,0,1,1]).join(',');
  $('source-player').src = await ticket(detail.media_url);
  $('source-player').onloadedmetadata = () => { $('source-player').currentTime = r.start; };
  $('source-player').ontimeupdate = () => { if ($('source-player').currentTime >= Number($('clip-end').value) && !$('source-player').paused) $('source-player').pause(); };
  $('source-note').textContent = 'Source recording. Playback stops at the selected end.';
  $('transcript').textContent = c.text || '';
  $('reasons').innerHTML = `<p>${escapeHtml(selected.about.summary || '')}</p>` + Object.entries(c.jev || {}).map(([key,answer]) => `<p><strong>${escapeHtml(key)}</strong> ${escapeHtml(JSON.stringify(answer))}</p>`).join('');
  await updateClipState(selected.state); renderClips();
}
async function updateClipState(state) {
  if (!selected) return;
  $('clip-status').textContent = state.status; $('approve').disabled = !state.preview_ok;
  $('render-status').textContent = state.render_error || (state.render === 'running' ? 'Rendering locally…' : state.preview_ok ? 'Previews match saved edits. Watch both before approval.' : 'Render previews before approving.');
  for (const [id,path] of [['portrait',state.preview_url],['landscape',state.landscape_url]]) {
    if (path && $(id).dataset.path !== path) { $(id).src = await ticket(path); $(id).dataset.path = path; }
    if (!path && $(id).getAttribute('src')) { $(id).removeAttribute('src'); $(id).load(); delete $(id).dataset.path; }
  }
}
function clipPath(suffix = '') { if (!selected) throw new Error('Select a moment first.'); return `/jobs/${detail.job.id}/clips/${selected.candidate.id}${suffix}`; }
async function saveClip() {
  let captions,drafts;
  try { captions=JSON.parse($('clip-captions').value); drafts=JSON.parse($('clip-drafts').value); } catch { throw new Error('Captions and posting drafts must be valid JSON.'); }
  if (!Array.isArray(captions) || !drafts || Array.isArray(drafts) || typeof drafts !== 'object') throw new Error('Use a captions array and a posting drafts object.');
  const mode = $('layout-mode').value;
  const state = await api(clipPath(),{method:'POST',body:{start:Number($('clip-start').value),end:Number($('clip-end').value),title:$('clip-heading').value,captions,drafts,layout:mode === 'crop' ? {mode,crop:$('crop-box').value.split(',').map(Number)} : {mode}}});
  await updateClipState(state);
}
$('save-clip').onclick = () => perform(saveClip);
$('render').onclick = () => perform(async () => { await saveClip(); await updateClipState(await api(clipPath('/preview'),{method:'POST'})); });
for (const [id,decision] of [['approve','approve'],['reject','reject']]) $(id).onclick = () => perform(async () => { await saveClip(); await updateClipState(await api(clipPath('/decision'),{method:'POST',body:{decision}})); await refreshDetail(); });
$('next').onclick = () => perform(async () => { const clips = filteredClips(), index=clips.findIndex(c => c.id === selected?.candidate.id); if (clips[index+1]) await openClip(clips[index+1].id); });
async function refreshDetail() { if (detail) { detail=await api('/jobs/'+detail.job.id); updateJob(); } }
$('authorize').onclick = () => perform(async () => { await api(`/jobs/${detail.job.id}/authorize`,{method:'POST'}); await refreshDetail(); });
$('resume').onclick = () => perform(async () => { await api(`/jobs/${detail.job.id}/resume`,{method:'POST'}); await refreshDetail(); });
$('save-criteria').onclick = () => perform(async () => { const result=await api(`/jobs/${detail.job.id}/profile`,{method:'POST',body:{...JSON.parse($('job-profile').value),intent:$('job-intent').value}}); detail.job.profile=result.profile; });
$('suggest-criteria').onclick = () => perform(async () => {
  if (!confirm('Authorize this AI criteria call within the $1.50 per-video cap? Transcript excerpts will go to your configured provider.')) return;
  const result=await api(`/jobs/${detail.job.id}/suggest-profile`,{method:'POST',body:{authorize:true,intent:$('job-intent').value}});
  detail.job.profile=result.profile; $('job-intent').value=result.profile.intent;
  $('job-profile').value=JSON.stringify(result.profile,null,2);
  $('criteria-editor').open=true;
});
$('export').onclick = () => perform(async () => { await api(`/jobs/${detail.job.id}/export`,{method:'POST'}); location.hash='exports'; await loadExports(); });
async function loadExports() {
  const result=await api(`/jobs/${detail.job.id}/exports`); $('packages').innerHTML='';
  const status=document.createElement('p'); status.textContent=result.task.error || (result.task.state === 'running' ? 'Exporting locally…' : result.files.length ? 'Download package files:' : 'No package exported yet.'); $('packages').append(status);
  for (const file of result.files) { const button=document.createElement('button'); button.textContent=file.name; button.onclick=()=>perform(async()=>{ const response=await fetch(await ticket(file.url)); if(!response.ok) throw new Error('Download failed. Refresh the package and try again.'); const objectUrl=URL.createObjectURL(await response.blob()); const link=document.createElement('a'); link.href=objectUrl; link.download=file.name.split('/').pop(); link.click(); setTimeout(()=>URL.revokeObjectURL(objectUrl),60000); }); $('packages').append(button,document.createTextNode(' ')); }
}
setInterval(async () => {
  if (!connected || busy || document.hidden) return;
  try {
    if (detail) { await refreshDetail(); if (selected) await updateClipState(await api(clipPath('/state'))); if (location.hash === '#exports') await loadExports(); }
    else await loadJobs();
  } catch (error) { notice(error.message || 'Companion disconnected. Restart it and reconnect with its new pairing code.'); }
},4000);
