// frontend/app.js

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  videos: [],          // VideoInfo objects from last /api/fetch
  channel: null,
  playlistTitle: null,
  selectedIds: new Set(),
  selectedFields: new Set(),
  pollTimer: null,
  currentJobId: null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const urlInput       = document.getElementById('url-input');
const fetchBtn       = document.getElementById('fetch-btn');
const outputFolder   = document.getElementById('output-folder');
const statusBar      = document.getElementById('status-bar');
const emptyState     = document.getElementById('empty-state');
const videoTable     = document.getElementById('video-table');
const videoTbody     = document.getElementById('video-tbody');
const selectAll      = document.getElementById('select-all');
const bottomBar      = document.getElementById('bottom-bar');
const selectionCount = document.getElementById('selection-count');
const downloadBtn    = document.getElementById('download-btn');
const fieldsList     = document.getElementById('fields-list');

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  await loadFields();
  fetchBtn.addEventListener('click', handleFetch);
  urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleFetch(); });
  selectAll.addEventListener('change', handleSelectAll);
  downloadBtn.addEventListener('click', handleDownload);
}

// ── Fields panel ───────────────────────────────────────────────────────────
const DEFAULT_FIELDS = new Set(['title', 'upload_date', 'channel', 'duration']);

async function loadFields() {
  const res = await fetch('/api/fields');
  const fields = await res.json();
  fieldsList.innerHTML = '';
  for (const field of fields) {
    const label = document.createElement('label');
    label.className = 'field-label';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = field;
    cb.checked = DEFAULT_FIELDS.has(field);
    if (cb.checked) state.selectedFields.add(field);
    cb.addEventListener('change', () => {
      if (cb.checked) state.selectedFields.add(field);
      else state.selectedFields.delete(field);
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(field));
    fieldsList.appendChild(label);
  }
}

// ── Fetch videos ───────────────────────────────────────────────────────────
async function handleFetch() {
  const url = urlInput.value.trim();
  if (!url) return;
  setStatus('Fetching…');
  fetchBtn.disabled = true;

  try {
    const res = await fetch('/api/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    state.videos = data.videos;
    state.channel = data.channel;
    state.playlistTitle = data.playlist_title;
    state.selectedIds.clear();
    renderTable();
    setStatus(`Fetched ${data.videos.length} video(s)`);
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    fetchBtn.disabled = false;
  }
}

// ── Table rendering ────────────────────────────────────────────────────────
function renderTable() {
  videoTbody.innerHTML = '';

  if (state.videos.length === 0) {
    emptyState.classList.remove('hidden');
    videoTable.classList.add('hidden');
    bottomBar.classList.add('hidden');
    return;
  }

  emptyState.classList.add('hidden');
  videoTable.classList.remove('hidden');
  bottomBar.classList.remove('hidden');

  for (const video of state.videos) {
    const tr = document.createElement('tr');
    tr.dataset.videoId = video.video_id;

    const checkTd = document.createElement('td');
    checkTd.className = 'col-check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.addEventListener('change', () => toggleSelect(video.video_id, cb.checked));
    checkTd.appendChild(cb);

    const titleTd  = document.createElement('td');
    const titleLink = document.createElement('a');
    titleLink.href = video.url;
    titleLink.target = '_blank';
    titleLink.textContent = video.title;
    titleLink.style.color = '#89b4fa';
    titleLink.style.textDecoration = 'none';
    titleTd.appendChild(titleLink);

    const dateTd    = makeTd(video.upload_date || '—', 'muted');
    const channelTd = makeTd(video.channel || '—', 'muted');
    const durTd     = makeTd(formatDuration(video.duration), 'muted');
    const statusTd  = document.createElement('td');
    statusTd.className = 'col-status';

    tr.appendChild(checkTd);
    tr.appendChild(titleTd);
    tr.appendChild(dateTd);
    tr.appendChild(channelTd);
    tr.appendChild(durTd);
    tr.appendChild(statusTd);
    videoTbody.appendChild(tr);
  }

  updateSelectionUI();
}

function makeTd(text, cls) {
  const td = document.createElement('td');
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function formatDuration(seconds) {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Selection logic ────────────────────────────────────────────────────────
function toggleSelect(videoId, checked) {
  if (checked) state.selectedIds.add(videoId);
  else state.selectedIds.delete(videoId);
  updateSelectionUI();
}

function handleSelectAll() {
  const checked = selectAll.checked;
  for (const video of state.videos) {
    if (checked) state.selectedIds.add(video.video_id);
    else state.selectedIds.delete(video.video_id);
  }
  for (const cb of videoTbody.querySelectorAll('input[type="checkbox"]')) {
    cb.checked = checked;
  }
  updateSelectionUI();
}

function updateSelectionUI() {
  const count = state.selectedIds.size;
  selectionCount.textContent = `${count} selected`;
  downloadBtn.disabled = count === 0;
  selectAll.checked = count > 0 && count === state.videos.length;
  selectAll.indeterminate = count > 0 && count < state.videos.length;
}

// ── Status bar ─────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
  statusBar.textContent = msg;
  statusBar.classList.remove('hidden', 'error');
  if (isError) statusBar.classList.add('error');
}

init();

// ── Download + progress ────────────────────────────────────────────────────
async function handleDownload() {
  const folder = outputFolder.value.trim();
  if (!folder) {
    setStatus('Please enter an output folder path.', true);
    return;
  }
  if (state.selectedIds.size === 0) return;

  const videoUrls = {};
  for (const video of state.videos) {
    if (state.selectedIds.has(video.video_id)) {
      videoUrls[video.video_id] = video.url;
    }
  }

  // Mark all selected rows as pending
  for (const videoId of state.selectedIds) {
    setRowStatus(videoId, 'pending');
  }
  downloadBtn.disabled = true;
  setStatus('Starting download…');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_ids: [...state.selectedIds],
        video_urls: videoUrls,
        fields: [...state.selectedFields],
        output_folder: folder,
        channel_name: state.channel,
        playlist_title: state.playlistTitle,
      }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const { job_id } = await res.json();
    state.currentJobId = job_id;
    startPolling(job_id);
  } catch (err) {
    setStatus(`Download failed: ${err.message}`, true);
    downloadBtn.disabled = false;
  }
}

function startPolling(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => pollProgress(jobId), 2000);
}

async function pollProgress(jobId) {
  try {
    const res = await fetch(`/api/progress/${jobId}`);
    const data = await res.json();

    for (const v of data.videos) {
      setRowStatus(v.video_id, v.status, v.error);
    }

    const total    = data.videos.length;
    const done     = data.videos.filter(v => v.status === 'done').length;
    const errors   = data.videos.filter(v => v.status === 'error').length;
    const active   = data.videos.filter(v => v.status === 'downloading').length;

    if (active > 0) {
      setStatus(`Downloading… ${done}/${total} done`);
    }

    if (data.status === 'done') {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      downloadBtn.disabled = false;
      const msg = errors > 0
        ? `Done. ${done} downloaded, ${errors} failed.`
        : `Done. ${done} video(s) downloaded to ${outputFolder.value.trim()}`;
      setStatus(msg, errors > 0);
    }
  } catch (err) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    setStatus(`Polling error: ${err.message}`, true);
    downloadBtn.disabled = false;
  }
}

function setRowStatus(videoId, status, errorMsg) {
  const tr = videoTbody.querySelector(`tr[data-video-id="${videoId}"]`);
  if (!tr) return;
  const statusTd = tr.querySelector('.col-status');
  if (!statusTd) return;

  const labels = {
    pending:     'Pending',
    downloading: 'Downloading',
    done:        'Done',
    error:       errorMsg ? `Error: ${errorMsg}` : 'Error',
  };

  statusTd.innerHTML = `<span class="status-badge status-${status}">${labels[status] || status}</span>`;
}
