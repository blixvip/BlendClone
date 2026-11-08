const $ = id => document.getElementById(id);
const state = { jobs: [], active: null, health: null, importing: false, single: false, previewIndex: 0, operation: null, epoch: 0, offline: false };
const running = job => ['queued', 'running'].includes(job.status);
const previewing = job => Boolean(job?.preview_frames?.length && job.status !== 'completed');
const text = (id, value) => { $(id).textContent = value; };
function error(message) { text('error', message); $('error').hidden = !message; }
function formatTime(value) { const total = Math.floor(Math.max(0, Number.isFinite(value) ? value : 0)); return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`; }
function formatPreciseTime(value) { const total = Math.round(Math.max(0, Number.isFinite(value) ? value : 0) * 1000); return `${Math.floor(total / 60000)}:${String(Math.floor(total / 1000) % 60).padStart(2, '0')}.${String(total % 1000).padStart(3, '0')}`; }
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
    const isOpen = job.id === state.active?.id;
    button.className = `project-item${isOpen ? ' selected' : ''}`;
    if (isOpen) button.setAttribute('aria-current', 'true');
    const title = document.createElement('strong'); title.textContent = job.title;
    const sub = document.createElement('small');
    const status = document.createElement('span'); status.textContent = job.status === 'preview' ? 'Preview ready' : job.status;
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
  pause(); state.epoch++; state.active = null; location.hash = ''; $('create-view').hidden = false; $('project-view').hidden = true;
  text('breadcrumb', 'New remake'); error(''); renderLibrary();
}
function artifactURL(job, name, download = false) { return name ? `/api/jobs/${job.id}/files/${name.split('/').map(encodeURIComponent).join('/')}${download ? '?download=true' : ''}` : ''; }
function fileURL(job, kind, download = false) { return artifactURL(job, job.artifacts?.[kind], download); }
function setVideo(id, url) {
  const video = $(id);
  if (video.getAttribute('src') !== url) {
    if (url) video.src = url;
    else { video.removeAttribute('src'); video.load(); }
  }
}
function showProject(job) {
  const changed = state.active?.id !== job.id;
  const enteredPreview = state.active?.status !== 'preview' && job.status === 'preview';
  if (changed) { pause(); state.epoch++; state.previewIndex = 0; }
  state.active = job;
  if (changed || enteredPreview) $('render-quality').value = job.quality || 'draft';
  const index = state.jobs.findIndex(item => item.id === job.id);
  if (index >= 0) state.jobs[index] = job;
  $('create-view').hidden = true; $('project-view').hidden = false;
  text('breadcrumb', job.title); text('job-title', job.title); text('job-status', job.status === 'preview' ? 'Preview ready' : job.status);
  $('job-status').className = `badge ${job.status}`;
  text('job-message', job.message); text('job-percent', `${job.progress}%`); $('progress').value = job.progress;
  $('cancel').hidden = !running(job); $('retry').hidden = !['failed', 'cancelled', 'interrupted'].includes(job.status);
  $('job-progress').hidden = ['completed', 'preview'].includes(job.status);
  $('preview-notice').hidden = job.status !== 'preview';
  $('render-form').hidden = job.status !== 'preview';
  setVideo('reference-video', fileURL(job, 'reference')); setVideo('remake-video', fileURL(job, 'video'));
  $('reference-empty').hidden = Boolean(job.artifacts.reference); $('remake-empty').hidden = Boolean(job.artifacts.video);
  for (const id of ['play', 'seek', 'previous-frame', 'next-frame']) $(id).disabled = !job.artifacts.reference;
  const exports = ['blend', 'video', 'comparison', 'project'];
  $('downloads').hidden = !exports.some(kind => job.artifacts[kind]);
  for (const kind of exports) { const link = $('download-' + kind); link.hidden = !job.artifacts[kind]; link.href = fileURL(job, kind, true); }
  $('download-note').hidden = job.status === 'completed' || !job.artifacts.video;
  $('revise-form').hidden = !['completed', 'preview'].includes(job.status); text('job-summary', job.summary || '');
  const returnsPreview = job.preview_first !== false || job.status === 'preview';
  text('revise-submit', returnsPreview ? 'Revise preview ↗' : 'Revise & render ↗');
  text('revision-hint', returnsPreview ? 'Corrections create new still previews for you to compare.' : 'Corrections rebuild and render the full video with this project’s settings.');
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
  renderCoverage(job); renderPreview(); updateActionButtons(); renderLibrary(); updateTime();
}
function renderFidelity(job) {
  const score = job.status === 'completed' ? job.fidelity : null;
  $('fidelity-score').hidden = !score;
  if (!score) return;
  const verdicts = {
    'metrics-pass': `Every frame passes the calibrated gates (${score.frames.toLocaleString()} of ${score.frames.toLocaleString()}) · watch it side by side before calling it 1:1`,
    'metrics-pass-uncalibrated': `Every frame passes, but the gates are not calibrated yet`,
    approximate: `Approximate · ${Number(score.passing_frames).toLocaleString()} of ${Number(score.frames).toLocaleString()} frames pass`,
  };
  text('fidelity-verdict', verdicts[score.verdict] || 'Score unavailable');
  $('fidelity-score').classList.toggle('passing', score.verdict === 'metrics-pass');
  const lag = score.timing?.lag_frames || 0, m = score.metrics || {};
  const timing = !score.timing?.frame_count_match ? 'Frame count differs' : lag === 0 ? 'No overall timing offset detected' : `Estimated timing offset: ${Math.abs(lag)} frame${Math.abs(lag) === 1 ? '' : 's'} ${lag < 0 ? 'late' : 'early'}`;
  const parts = [timing];
  if (m.coarse_ssim) parts.push(`worst layout ${m.coarse_ssim.worst.toFixed(3)}`);
  if (m.delta_e) parts.push(`worst color ΔE ${m.delta_e.worst.toFixed(1)}`);
  if (score.worst_frames?.length) parts.push(`check frames ${score.worst_frames.join(', ')}`);
  text('fidelity-detail', parts.join(' · '));
}
function renderCoverage(job) {
  renderFidelity(job);
  const benchmark = job.benchmark;
  $('benchmark-review').hidden = !benchmark;
  if (benchmark) {
    text('benchmark-status', `Approximate · ${benchmark.rendered_frames} pilot frames rendered · full video incomplete · visual acceptance pending`);
    $('benchmark-link').href = fileURL(job, 'review');
    $('benchmark-link').hidden = !job.artifacts.review;
  }
  const analysis = job.analysis;
  $('analysis-coverage').hidden = !analysis;
  if (!analysis) return;
  text('analysis-machine', `${Number(analysis.frames || 0).toLocaleString()} frames scanned · ${Number(analysis.sheets || 0).toLocaleString()} contact sheets`);
  const reviewed = Number(analysis.reviewed_batches || 0), total = Number(analysis.total_batches || 0);
  text('analysis-visual', analysis.visual_review === 'complete' ? `Astra inspected ${reviewed} of ${total} sheet batches · visual review complete` : `Astra inspected ${reviewed} of ${total} sheet batches · visual review pending`);
}
function renderPreview() {
  const job = state.active, showing = previewing(job);
  $('preview-transport').hidden = !showing; $('video-transport').hidden = showing;
  for (const type of ['reference', 'remake']) { $(type + '-video').hidden = showing; $(type + '-still').hidden = !showing; }
  if (!showing) return;
  pause();
  const frames = job.preview_frames;
  state.previewIndex = Math.min(Math.max(state.previewIndex, 0), frames.length - 1);
  const frame = frames[state.previewIndex];
  for (const [type, path] of [['reference', frame.source], ['remake', frame.render]]) {
    const still = $(type + '-still'), url = artifactURL(job, path);
    if (still.getAttribute('src') !== url) still.src = url;
    still.alt = `${type === 'reference' ? 'Reference' : 'Blender render'} at ${formatPreciseTime(frame.time)}`;
    $(type + '-empty').hidden = true;
  }
  text('preview-time', formatPreciseTime(frame.time)); text('preview-position', `Preview ${state.previewIndex + 1} of ${frames.length}`);
  $('previous-preview').disabled = state.previewIndex === 0; $('next-preview').disabled = state.previewIndex === frames.length - 1;
}
function updateActionButtons() {
  const busy = state.operation?.id === state.active?.id;
  for (const id of ['cancel', 'retry', 'render-submit', 'revise-submit', 'render-quality']) $(id).disabled = busy;
}
async function mutateProject(action, payload) {
  if (!state.active || state.operation) return;
  const id = state.active.id, epoch = ++state.epoch;
  state.operation = { id, action }; updateActionButtons(); error('');
  try {
    const job = await api(`/api/jobs/${id}/${action}`, { method: 'POST', ...(payload ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}) });
    if (state.active?.id === id && state.epoch === epoch) {
      if (action === 'cancel') text('job-message', 'Cancelling the current step…');
      else { if (action === 'revise') $('revision-brief').value = ''; showProject(job); }
    }
  } catch (e) { if (state.active?.id === id) error(e.message); }
  finally { state.operation = null; updateActionButtons(); }
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
  data.set('preview_first', String($('preview-first').checked));
  state.importing = true; $('submit').disabled = true; text('submit', 'Importing reference…');
  try { const job = await api('/api/jobs', { method: 'POST', body: data }); await refreshJobs(); location.hash = job.id; showProject(job); }
  catch (e) { error(e.message); }
  finally { state.importing = false; $('submit').disabled = !(state.health?.blender && state.health?.codex && state.health?.ffmpeg); updateSubmitLabel(); }
});
function updateSubmitLabel() { text('submit', $('preview-first').checked ? 'Build preview ↗' : 'Rebuild in Blender ↗'); }
$('preview-first').addEventListener('change', updateSubmitLabel);
$('new-project').addEventListener('click', newProject); $('search').addEventListener('input', renderLibrary);
window.addEventListener('hashchange', openFromHash);
document.addEventListener('keydown', e => { if (e.key.toLowerCase() === 'n' && !e.ctrlKey && !e.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) newProject(); });
$('cancel').addEventListener('click', () => mutateProject('cancel'));
$('retry').addEventListener('click', () => mutateProject('retry'));
$('revise-form').addEventListener('submit', e => { e.preventDefault(); if (!$('revision-brief').value.trim()) return error('Describe a correction before revising.'); mutateProject('revise', { brief: $('revision-brief').value }); });
$('render-form').addEventListener('submit', e => { e.preventDefault(); mutateProject('render', { quality: $('render-quality').value }); });
$('previous-preview').addEventListener('click', () => { state.previewIndex--; renderPreview(); });
$('next-preview').addEventListener('click', () => { state.previewIndex++; renderPreview(); });
$('use-time').addEventListener('click', () => {
  const time = previewing(state.active) ? state.active.preview_frames[state.previewIndex].time : reference.currentTime;
  const field = $('revision-brief'), stamp = `At ${formatPreciseTime(time)}, `;
  if (field.value.length + stamp.length + 1 > field.maxLength) return error('Shorten the correction before adding a timestamp.');
  field.value += `${field.value ? '\n' : ''}${stamp}`; field.focus(); field.setSelectionRange(field.value.length, field.value.length);
});
const reference = $('reference-video'), remake = $('remake-video');
function pause() { reference.pause(); remake.pause(); text('play', '▶'); $('play').setAttribute('aria-label', 'Play comparison'); }
function updateTime() { const duration = Number.isFinite(reference.duration) ? reference.duration : state.active?.meta?.duration || 0; text('play-time', `${formatPreciseTime(reference.currentTime)} / ${formatTime(duration)}`); $('seek').max = duration || 1; $('seek').value = reference.currentTime || 0; }
function seekTo(time) { if (reference.readyState < 1) return; reference.currentTime = Math.max(0, Math.min(time, reference.duration)); if (remake.readyState >= 1) remake.currentTime = reference.currentTime; updateTime(); }
function stepFrame(direction) { pause(); const fps = Number(state.active?.meta?.fps) || 24; seekTo((Math.round(reference.currentTime * fps) + direction) / fps); }
$('previous-frame').addEventListener('click', () => stepFrame(-1)); $('next-frame').addEventListener('click', () => stepFrame(1));
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
$('seek').addEventListener('input', e => seekTo(Number(e.target.value)));
$('mute').addEventListener('click', () => { reference.muted = !reference.muted; text('mute', reference.muted ? 'Sound off' : 'Sound on'); $('mute').setAttribute('aria-pressed', reference.muted); });
$('speed').addEventListener('change', () => { reference.playbackRate = remake.playbackRate = Number($('speed').value); });
function setMode(single) { state.single = single; $('comparison').classList.toggle('single', single); for (const [id, active] of [['compare-mode', !single], ['rebuilt-mode', single]]) { $(id).classList.toggle('active', active); $(id).setAttribute('aria-pressed', active); } }
$('compare-mode').addEventListener('click', () => setMode(false)); $('rebuilt-mode').addEventListener('click', () => setMode(true));
async function poll() {
  try {
    if (state.active && running(state.active) && !state.operation) {
      const id = state.active.id, epoch = state.epoch, job = await api('/api/jobs/' + id);
      if (state.active?.id === id && state.epoch === epoch && !state.operation) { showProject(job); if (state.offline) { state.offline = false; error(''); } }
      if (!running(job)) await refreshJobs();
    }
  } catch (e) { state.offline = true; error('Connection lost. Reconnecting to your local workspace…'); }
  setTimeout(poll, 1600);
}
Promise.all([refreshHealth(), refreshJobs()]).then(openFromHash).catch(e => error(e.message));
setInterval(() => refreshHealth().catch(() => {}), 30000); poll();
