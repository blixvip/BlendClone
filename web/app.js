const $ = id => document.getElementById(id);
const state = { jobs: [], active: null, health: null, importing: false, single: false };
const running = job => ['queued', 'running'].includes(job.status);
const text = (id, value) => { $(id).textContent = value; };
function error(message) { text('error', message); $('error').hidden = !message; }
function formatTime(value) { const total = Math.floor(Math.max(0, Number.isFinite(value) ? value : 0)); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`; }
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'X-BlendRemake': '1', ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the reference, clip length, and settings.');
  return data;
}
function renderLibrary() {
  const query = $('search').value.toLowerCase();
  const fragment = document.createDocumentFragment();
  const matches = state.jobs.filter(job => job.title.toLowerCase().includes(query));
  for (const job of matches) {
    const button = document.createElement('button');
    button.className = `project-item${job.id === state.active?.id ? ' selected' : ''}`;
    const title = document.createElement('strong'); title.textContent = job.title;
    const sub = document.createElement('small');
    const status = document.createElement('span'); status.textContent = job.status;
    const date = document.createElement('span'); date.textContent = new Date(job.created).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    sub.append(status, date); button.append(title, sub);
    button.addEventListener('click', () => { location.hash = job.id; });
    fragment.append(button);
  }
  if (!matches.length) { const p = document.createElement('p'); p.className = 'library-empty'; p.textContent = query ? 'No matching projects.' : 'Your references and remakes will be saved here.'; fragment.append(p); }
  $('library').replaceChildren(fragment); text('project-count', state.jobs.length);
}
async function refreshJobs() { state.jobs = await api('/api/jobs'); renderLibrary(); }
async function refreshHealth() {
  state.health = await api('/api/health');
  const ready = state.health.blender && state.health.codex && state.health.ffmpeg;
  $('engine-dot').classList.toggle('ready', ready);
  text('engine-label', ready ? 'Blender + Astra connected' : 'Setup needed');
  const missing = [];
  if (!state.health.blender) missing.push('Install Blender 5.1 or set BLENDER_PATH.');
  if (!state.health.codex) missing.push('Connect ChatGPT by running codex login in your terminal.');
  if (!state.health.ffmpeg) missing.push('Install FFmpeg and ffprobe.');
  text('connection-warning', missing.join(' ')); $('connection-warning').hidden = ready;
  $('submit').disabled = !ready || state.importing;
}
function newProject() {
  pause(); state.active = null; location.hash = ''; $('create-view').hidden = false; $('project-view').hidden = true;
  text('breadcrumb', 'New remake'); error(''); renderLibrary();
}
function fileURL(job, kind, download = false) { const name = job.artifacts[kind]; return name ? `/api/jobs/${job.id}/files/${name}${download ? '?download=true' : ''}` : ''; }
function setVideo(id, url) {
  const video = $(id);
  if (video.getAttribute('src') !== url) {
    if (url) video.src = url;
    else { video.removeAttribute('src'); video.load(); }
  }
}
function showProject(job) {
  const changed = state.active?.id !== job.id;
  if (changed) pause();
  state.active = job;
  $('create-view').hidden = true; $('project-view').hidden = false;
  text('breadcrumb', job.title); text('job-title', job.title); text('job-status', job.status);
  $('job-status').className = `badge ${job.status}`;
  text('job-message', job.message); text('job-percent', `${job.progress}%`); $('progress').value = job.progress;
  $('cancel').hidden = !running(job); $('retry').hidden = running(job) || job.status === 'completed';
  $('job-progress').hidden = job.status === 'completed';
  setVideo('reference-video', fileURL(job, 'reference')); setVideo('remake-video', fileURL(job, 'video'));
  $('reference-empty').hidden = Boolean(job.artifacts.reference); $('remake-empty').hidden = Boolean(job.artifacts.video);
  $('play').disabled = !job.artifacts.reference; $('seek').disabled = !job.artifacts.reference;
  $('downloads').hidden = job.status !== 'completed';
  for (const kind of ['blend', 'video', 'comparison', 'project']) $('download-' + kind).href = fileURL(job, kind, true);
  $('revise-form').hidden = job.status !== 'completed'; text('job-summary', job.summary || '');
  if (changed) $('revision-brief').value = '';
  text('shot-count', job.shots ? `${job.shots.length} SHOT${job.shots.length === 1 ? '' : 'S'}` : '');
  const shots = (job.shots || []).map(shot => {
    const node = document.createElement('div'); node.className = 'shot';
    const heading = document.createElement('div'); heading.className = 'shot-title';
    const name = document.createElement('strong'); name.textContent = shot.name;
    const time = document.createElement('span'); time.textContent = `${shot.start.toFixed(1)}–${shot.end.toFixed(1)}s`;
    const desc = document.createElement('p'); desc.textContent = `${shot.description} · ${shot.objects} objects`;
    heading.append(name, time); node.append(heading, desc); return node;
  });
  if (!shots.length) { const node = document.createElement('p'); node.className = 'muted'; node.textContent = 'Scene analysis will appear here.'; shots.push(node); }
  $('shots').replaceChildren(...shots);
  const notes = job.limitations?.length ? job.limitations : ['Review the result against your reference before using it.'];
  $('limitations').replaceChildren(...notes.map(note => { const li = document.createElement('li'); li.textContent = note; return li; }));
  renderLibrary(); updateTime();
}
async function openFromHash() {
  const id = location.hash.slice(1);
  if (!/^[a-f0-9]{12}$/.test(id)) return newProject();
  try { const job = await api('/api/jobs/' + id); if (location.hash.slice(1) === id) showProject(job); } catch (e) { error(e.message); }
}
function selectFile(file) {
  text('file-label', file ? file.name : 'Drop your reference here');
  text('file-help', file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · selected` : 'MP4, MOV, WebM · up to 250 MB');
  $('clear-file').hidden = !file;
  if (file) $('url').value = '';
}
$('video').addEventListener('change', () => selectFile($('video').files[0]));
$('clear-file').addEventListener('click', () => { $('video').value = ''; selectFile(null); });
$('url').addEventListener('input', () => { if ($('url').value) { $('video').value = ''; selectFile(null); } });
for (const event of ['dragenter', 'dragover']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.add('drag'); });
for (const event of ['dragleave', 'drop']) $('dropzone').addEventListener(event, e => { e.preventDefault(); $('dropzone').classList.remove('drag'); });
$('dropzone').addEventListener('drop', e => { if (e.dataTransfer.files.length) { const transfer = new DataTransfer(); transfer.items.add(e.dataTransfer.files[0]); $('video').files = transfer.files; selectFile(transfer.files[0]); } });
$('import-form').addEventListener('submit', async e => {
  e.preventDefault(); error('');
  const file = $('video').files[0];
  if (!file && !$('url').value.trim()) return error('Add a reference video link or choose a file.');
  if (file?.size > 250 * 1024 * 1024) return error('Video exceeds 250 MB. Choose a smaller file.');
  const data = new FormData($('import-form'));
  if (!file) data.delete('video');
  data.set('audio', String($('audio').checked)); data.set('review', String($('review').checked));
  state.importing = true; $('submit').disabled = true; text('submit', 'Importing reference…');
  try { const job = await api('/api/jobs', { method: 'POST', body: data }); await refreshJobs(); location.hash = job.id; showProject(job); }
  catch (e) { error(e.message); }
  finally { state.importing = false; $('submit').disabled = false; text('submit', 'Rebuild in Blender ↗'); }
});
$('new-project').addEventListener('click', newProject); $('search').addEventListener('input', renderLibrary);
window.addEventListener('hashchange', openFromHash);
document.addEventListener('keydown', e => { if (e.key.toLowerCase() === 'n' && !e.ctrlKey && !e.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) newProject(); });
$('cancel').addEventListener('click', async () => { try { await api(`/api/jobs/${state.active.id}/cancel`, { method: 'POST' }); text('job-message', 'Cancelling the current step…'); } catch (e) { error(e.message); } });
$('retry').addEventListener('click', async () => { try { showProject(await api(`/api/jobs/${state.active.id}/retry`, { method: 'POST' })); } catch (e) { error(e.message); } });
$('revise-form').addEventListener('submit', async e => { e.preventDefault(); try { const job = await api(`/api/jobs/${state.active.id}/revise`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brief: $('revision-brief').value }) }); showProject(job); } catch (e) { error(e.message); } });
const reference = $('reference-video'), remake = $('remake-video');
function pause() { reference.pause(); remake.pause(); text('play', '▶'); $('play').setAttribute('aria-label', 'Play comparison'); }
function updateTime() { const duration = Number.isFinite(reference.duration) ? reference.duration : state.active?.meta?.duration || 0; text('play-time', `${formatTime(reference.currentTime)} / ${formatTime(duration)}`); $('seek').max = duration || 1; $('seek').value = reference.currentTime || 0; }
$('play').addEventListener('click', async () => {
  if (!reference.paused) return pause();
  try {
    if (reference.ended) { reference.currentTime = 0; if (remake.getAttribute('src')) remake.currentTime = 0; }
    if (remake.getAttribute('src')) { remake.currentTime = reference.currentTime; await remake.play(); }
    await reference.play(); text('play', 'Ⅱ'); $('play').setAttribute('aria-label', 'Pause comparison');
  } catch (e) { pause(); error('Playback could not start. Wait for the videos to load, then try again.'); }
});
reference.addEventListener('timeupdate', () => { updateTime(); if (!reference.paused && remake.readyState >= 2 && Math.abs(reference.currentTime - remake.currentTime) > .15) remake.currentTime = reference.currentTime; });
reference.addEventListener('loadedmetadata', updateTime); reference.addEventListener('ended', pause);
$('seek').addEventListener('input', e => { reference.currentTime = Number(e.target.value); if (remake.readyState >= 1) remake.currentTime = reference.currentTime; updateTime(); });
$('mute').addEventListener('click', () => { reference.muted = !reference.muted; text('mute', reference.muted ? 'Sound off' : 'Sound on'); $('mute').setAttribute('aria-pressed', reference.muted); });
$('speed').addEventListener('change', () => { reference.playbackRate = remake.playbackRate = Number($('speed').value); });
function setMode(single) { state.single = single; $('comparison').classList.toggle('single', single); for (const [id, active] of [['compare-mode', !single], ['rebuilt-mode', single]]) { $(id).classList.toggle('active', active); $(id).setAttribute('aria-pressed', active); } }
$('compare-mode').addEventListener('click', () => setMode(false)); $('rebuilt-mode').addEventListener('click', () => setMode(true));
async function poll() {
  try { if (state.active && running(state.active)) { const id = state.active.id; const job = await api('/api/jobs/' + id); if (state.active?.id === id) showProject(job); if (!running(job)) await refreshJobs(); } }
  catch (e) { error('Connection lost. Reconnecting to your local workspace…'); }
  setTimeout(poll, 1600);
}
Promise.all([refreshHealth(), refreshJobs()]).then(openFromHash).catch(e => error(e.message));
setInterval(() => refreshHealth().catch(() => {}), 30000); poll();
