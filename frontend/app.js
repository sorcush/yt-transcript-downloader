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
  dateAbort: null,     // AbortController for in-flight /api/dates stream
  sort: { col: null, dir: 'asc' },
  activeFavoriteId: null,
  favorites: [],
  downloadTranscript: true,
  downloadAudio: false,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const urlInput       = document.getElementById('url-input');
const fetchBtn       = document.getElementById('fetch-btn');
const outputFolder   = document.getElementById('output-folder');
const browserSelect  = document.getElementById('browser-select');
const browseBtn      = document.getElementById('browse-btn');
const emptyState     = document.getElementById('empty-state');
const videoTable     = document.getElementById('video-table');
const videoTbody     = document.getElementById('video-tbody');
const selectAll      = document.getElementById('select-all');
const bottomBar      = document.getElementById('bottom-bar');
const selectionCount = document.getElementById('selection-count');
const downloadBtn    = document.getElementById('download-btn');
const fieldsList     = document.getElementById('fields-list');
const fetchedChip    = document.getElementById('fetched-chip');
const datesChip      = document.getElementById('dates-chip');
const datesChipText  = document.getElementById('dates-chip-text');
const datesStopBtn   = document.getElementById('dates-stop-btn');
const favoritesSelect = document.getElementById('favorites-select');
const renameFavBtn   = document.getElementById('rename-fav-btn');
const deleteFavBtn   = document.getElementById('delete-fav-btn');
const saveFavBtn     = document.getElementById('save-fav-btn');
const favNameInput   = document.getElementById('fav-name-input');
const favNameConfirm = document.getElementById('fav-name-confirm');
const openFolderBtn  = document.getElementById('open-folder-btn');
const copyPathBtn    = document.getElementById('copy-path-btn');
const dlTranscript   = document.getElementById('dl-transcript');
const dlAudio        = document.getElementById('dl-audio');

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  // Register event listeners first so they work even if loadFields() fails
  fetchBtn.addEventListener('click', handleFetch);
  urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleFetch(); });
  browseBtn.addEventListener('click', handleBrowse);
  selectAll.addEventListener('change', handleSelectAll);
  downloadBtn.addEventListener('click', handleDownload);
  for (const th of videoTable.querySelectorAll('th[data-sort-col]')) {
    th.addEventListener('click', () => handleSortClick(th.dataset.sortCol));
  }
  datesStopBtn.addEventListener('click', () => {
    if (state.dateAbort) state.dateAbort.abort();
  });
  favoritesSelect.addEventListener('change', handleFavoritePick);
  saveFavBtn.addEventListener('click', showSaveFavField);
  favNameConfirm.addEventListener('click', handleSaveFavorite);
  favNameInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSaveFavorite(); });
  renameFavBtn.addEventListener('click', handleRenameFavorite);
  deleteFavBtn.addEventListener('click', handleDeleteFavorite);
  urlInput.addEventListener('input', () => {
    if (state.activeFavoriteId != null) { state.activeFavoriteId = null; renderFavoritesDropdown(); }
  });
  openFolderBtn.addEventListener('click', handleOpenFolder);
  copyPathBtn.addEventListener('click', handleCopyPath);
  dlTranscript.addEventListener('change', () => { state.downloadTranscript = dlTranscript.checked; updateSelectionUI(); });
  dlAudio.addEventListener('change', () => { state.downloadAudio = dlAudio.checked; updateSelectionUI(); });
  await loadFavorites();
  await loadFields();
}

// ── Fields panel ───────────────────────────────────────────────────────────
const DEFAULT_FIELDS = new Set(['title', 'description', 'upload_date', 'webpage_url']);

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

// ── Browse folder ──────────────────────────────────────────────────────────
async function handleBrowse() {
  browseBtn.disabled = true;
  setStatus('Opening folder picker…');
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 120000);
    const res = await fetch('/api/pick-folder', { signal: controller.signal });
    clearTimeout(timeout);
    if (!res.ok) {
      let detail = `Server error: ${res.status}`;
      try {
        const body = await res.json();
        if (body?.detail) detail = body.detail;
      } catch {
        // If response body is not JSON, keep fallback detail.
      }
      throw new Error(detail);
    }

    const { folder, cancelled } = await res.json();
    if (folder) {
      outputFolder.value = folder;
      setStatus(`Output folder set to ${folder}`);
    } else if (cancelled) {
      setStatus('Folder selection canceled.');
    } else {
      setStatus('No folder selected.', true);
    }
  } catch (err) {
    if (err.name === 'AbortError') {
      setStatus('Folder picker timed out.', true);
      return;
    }
    setStatus(`Browse failed: ${err.message}`, true);
  } finally {
    browseBtn.disabled = false;
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
      body: JSON.stringify({ url, cookies_browser: browserSelect.value || null }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    state.videos = state.activeFavoriteId != null
      ? mergeFavoriteVideos(data.videos)
      : data.videos;
    state.channel = data.channel;
    state.playlistTitle = data.playlist_title;
    state.selectedIds.clear();
    renderTable();
    fetchedChip.textContent = `✓ ${state.videos.length} fetched`;
    fetchedChip.classList.remove('error');
    fetchedChip.classList.add('visible');
    if (state.activeFavoriteId != null) await persistActiveFavorite();
    fetchDatesLazy(state.videos);
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    fetchBtn.disabled = false;
  }
}

// ── Sorting ─────────────────────────────────────────────────────────────────
function handleSortClick(col) {
  if (state.sort.col === col) {
    state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    state.sort.col = col;
    state.sort.dir = 'asc';
  }
  renderTable();
}

function sortedVideos() {
  const { col, dir } = state.sort;
  if (!col) return state.videos;
  const factor = dir === 'asc' ? 1 : -1;
  return [...state.videos].sort((a, b) => {
    const av = a[col], bv = b[col];
    const aEmpty = av == null || av === '' || av === '…' || av === '—';
    const bEmpty = bv == null || bv === '' || bv === '…' || bv === '—';
    if (aEmpty && bEmpty) return 0;
    if (aEmpty) return 1;
    if (bEmpty) return -1;
    if (col === 'duration') return factor * (av - bv);
    return factor * String(av).localeCompare(String(bv));
  });
}

function updateSortHeaders() {
  for (const th of videoTable.querySelectorAll('th[data-sort-col]')) {
    const col = th.dataset.sortCol;
    const isActive = col === state.sort.col;
    th.innerHTML = isActive
      ? `${th.dataset.label} <span class="sort-icon active">${state.sort.dir === 'asc' ? '▲' : '▼'}</span>`
      : `${th.dataset.label} <span class="sort-icon">⇅</span>`;
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
  saveFavBtn.disabled = !(state.playlistTitle || state.channel);
  updateSortHeaders();

  for (const video of sortedVideos()) {
    const tr = document.createElement('tr');
    tr.dataset.videoId = video.video_id;

    const checkTd = document.createElement('td');
    checkTd.className = 'col-check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.addEventListener('change', () => toggleSelect(video.video_id, cb.checked));
    checkTd.appendChild(cb);

    const titleTd  = document.createElement('td');
    titleTd.className = 'col-title';
    const titleLink = document.createElement('a');
    titleLink.href = video.url;
    titleLink.target = '_blank';
    titleLink.textContent = video.title;
    titleLink.style.color = '#89b4fa';
    titleLink.style.textDecoration = 'none';
    titleTd.appendChild(titleLink);

    const dateTd    = makeTd(video.upload_date || '…', 'col-date muted');
    const channelTd = makeTd(video.channel || '—', 'col-channel muted');
    const durTd     = makeTd(formatDuration(video.duration), 'col-duration muted');
    const statusTd  = document.createElement('td');
    statusTd.className = 'col-status';
    renderBadges(statusTd, video.has_transcript, video.has_audio);

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
  downloadBtn.disabled = count === 0 || (!state.downloadTranscript && !state.downloadAudio);
  selectAll.checked = count > 0 && count === state.videos.length;
  selectAll.indeterminate = count > 0 && count < state.videos.length;
}

// ── Status display ─────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
  fetchedChip.textContent = msg;
  fetchedChip.classList.toggle('error', isError);
  fetchedChip.classList.add('visible');
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
        cookies_browser: browserSelect.value || null,
        download_transcript: state.downloadTranscript,
        download_audio: state.downloadAudio,
        favorite_id: state.activeFavoriteId,
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
      // Update the badge flags BEFORE rendering status, since setRowStatus reads
      // them to draw the T/A badges for a done row. (Otherwise the last video to
      // finish renders empty: polling stops once the job is done, so there's no
      // later cycle to correct it.)
      if (v.status === 'done') {
        const video = state.videos.find(x => x.video_id === v.video_id);
        if (video) {
          if (state.downloadTranscript) video.has_transcript = true;
          if (state.downloadAudio) video.has_audio = true;
        }
      }
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

// ── Lazy date loading ───────────────────────────────────────────────────────
async function fetchDatesLazy(videos) {
  if (state.dateAbort) state.dateAbort.abort();

  const needsDates = videos.filter(v => !v.upload_date);
  if (needsDates.length === 0) return;

  const total = needsDates.length;
  let loaded = 0;

  state.dateAbort = new AbortController();
  datesChipText.textContent = `Dates 0/${total}`;
  datesChip.classList.add('visible');

  try {
    const res = await fetch('/api/dates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ videos: needsDates.map(v => ({ video_id: v.video_id, url: v.url })), cookies_browser: browserSelect.value || null }),
      signal: state.dateAbort.signal,
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const { video_id, upload_date } = JSON.parse(line.slice(6));
          updateDateCell(video_id, upload_date);
          loaded++;
          datesChipText.textContent = `Dates ${loaded}/${total}`;
        }
      }
    }
  } catch (err) {
    if (err.name !== 'AbortError') console.error('Date fetch error:', err);
  } finally {
    datesChip.classList.remove('visible');
    if (state.activeFavoriteId != null) persistActiveFavorite();
  }
}

function updateDateCell(videoId, date) {
  const video = state.videos.find(v => v.video_id === videoId);
  if (video) video.upload_date = date;
  const tr = videoTbody.querySelector(`tr[data-video-id="${videoId}"]`);
  if (!tr) return;
  const td = tr.querySelector('.col-date');
  if (td) td.textContent = date || '—';
}

function setRowStatus(videoId, status, errorMsg) {
  const tr = videoTbody.querySelector(`tr[data-video-id="${videoId}"]`);
  if (!tr) return;
  const statusTd = tr.querySelector('.col-status');
  if (!statusTd) return;

  if (status === 'done') {
    const video = state.videos.find(x => x.video_id === videoId);
    renderBadges(statusTd, video && video.has_transcript, video && video.has_audio);
    return;
  }

  const labels = {
    pending:     'Pending',
    downloading: 'Downloading',
    error:       errorMsg ? `Error: ${errorMsg}` : 'Error',
  };

  statusTd.innerHTML = `<span class="status-badge status-${status}">${labels[status] || status}</span>`;
}

function renderBadges(td, hasTranscript, hasAudio) {
  td.innerHTML = '';
  if (hasTranscript) td.appendChild(makeBadge('T', 'badge-transcript'));
  if (hasAudio) td.appendChild(makeBadge('A', 'badge-audio'));
}

function makeBadge(text, cls) {
  const span = document.createElement('span');
  span.className = `dl-badge ${cls}`;
  span.textContent = text;
  return span;
}

// ── Favorites ────────────────────────────────────────────────────────────────
async function loadFavorites() {
  try {
    const res = await fetch('/api/favorites');
    state.favorites = await res.json();
    renderFavoritesDropdown();
  } catch (err) {
    console.error('Failed to load favorites:', err);
  }
}

function renderFavoritesDropdown() {
  favoritesSelect.innerHTML = '<option value="">★ Favorites…</option>';
  for (const fav of state.favorites) {
    const opt = document.createElement('option');
    opt.value = String(fav.id);
    opt.textContent = fav.name;
    favoritesSelect.appendChild(opt);
  }
  favoritesSelect.value = state.activeFavoriteId ? String(state.activeFavoriteId) : '';
  const hasActive = state.activeFavoriteId != null;
  renameFavBtn.disabled = !hasActive;
  deleteFavBtn.disabled = !hasActive;
}

async function handleFavoritePick() {
  const id = favoritesSelect.value;
  if (!id) {
    state.activeFavoriteId = null;
    renderFavoritesDropdown();
    return;
  }
  state.activeFavoriteId = Number(id);
  const res = await fetch(`/api/favorites/${id}`);
  if (!res.ok) { setStatus('Failed to load favorite.', true); return; }
  const fav = await res.json();
  state.videos = fav.videos;
  state.selectedIds.clear();
  urlInput.value = fav.url;
  if (fav.output_folder) outputFolder.value = fav.output_folder;
  renderTable();
  renderFavoritesDropdown();
  setStatus(`Loaded "${fav.name}" (${fav.videos.length} videos)`);
}

function showSaveFavField() {
  favNameInput.value = state.playlistTitle || state.channel || '';
  favNameInput.classList.remove('hidden');
  favNameConfirm.classList.remove('hidden');
  favNameInput.focus();
}

function hideSaveFavField() {
  favNameInput.classList.add('hidden');
  favNameConfirm.classList.add('hidden');
}

async function handleSaveFavorite() {
  const name = favNameInput.value.trim();
  if (!name) { setStatus('Enter a name for the favorite.', true); return; }
  const payload = {
    url: urlInput.value.trim(),
    name,
    source_type: state.playlistTitle ? 'playlist' : 'channel',
    output_folder: outputFolder.value.trim() || null,
    videos: state.videos,
  };
  try {
    const res = await fetch('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Server error: ${res.status}`);
    }
    const { id } = await res.json();
    state.activeFavoriteId = id;
    hideSaveFavField();
    await loadFavorites();
    setStatus(`Saved "${name}" to favorites.`);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`, true);
  }
}

async function handleRenameFavorite() {
  if (state.activeFavoriteId == null) return;
  const current = state.favorites.find(f => f.id === state.activeFavoriteId);
  const name = prompt('Rename favorite:', current ? current.name : '');
  if (!name || !name.trim()) return;
  await fetch(`/api/favorites/${state.activeFavoriteId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  });
  await loadFavorites();
  setStatus(`Renamed to "${name.trim()}".`);
}

async function handleDeleteFavorite() {
  if (state.activeFavoriteId == null) return;
  const current = state.favorites.find(f => f.id === state.activeFavoriteId);
  if (!confirm(`Delete favorite "${current ? current.name : ''}"?`)) return;
  await fetch(`/api/favorites/${state.activeFavoriteId}`, { method: 'DELETE' });
  state.activeFavoriteId = null;
  await loadFavorites();
  setStatus('Favorite deleted.');
}

// Merge a fresh fetch into the active favorite's saved videos: preserve
// download badges + known dates for existing videos, and keep videos that
// dropped out of the playlist.
function mergeFavoriteVideos(fetched) {
  const existing = new Map(state.videos.map(v => [v.video_id, v]));
  const seen = new Set();
  const merged = [];
  for (const f of fetched) {
    const prev = existing.get(f.video_id);
    merged.push({
      ...f,
      upload_date: f.upload_date || (prev && prev.upload_date) || null,
      has_transcript: prev ? prev.has_transcript : false,
      has_audio: prev ? prev.has_audio : false,
    });
    seen.add(f.video_id);
  }
  for (const v of state.videos) {
    if (!seen.has(v.video_id)) merged.push(v);  // kept: removed from playlist
  }
  return merged;
}

// Upsert the current video list into the active favorite (preserves flags
// server-side; updates dates as they fill in).
async function persistActiveFavorite() {
  if (state.activeFavoriteId == null) return;
  const fav = state.favorites.find(f => f.id === state.activeFavoriteId);
  if (!fav) return;
  try {
    await fetch('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: fav.url,
        name: fav.name,
        source_type: fav.source_type,
        output_folder: outputFolder.value.trim() || null,
        videos: state.videos,
      }),
    });
  } catch (err) {
    console.error('Failed to persist favorite:', err);
  }
}

// ── Output folder actions ────────────────────────────────────────────────────
async function handleOpenFolder() {
  const folder = outputFolder.value.trim();
  if (!folder) { setStatus('No output folder to open.', true); return; }
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Server error: ${res.status}`);
    }
  } catch (err) {
    setStatus(`Open failed: ${err.message}`, true);
  }
}

async function handleCopyPath() {
  const folder = outputFolder.value.trim();
  if (!folder) { setStatus('No output folder to copy.', true); return; }
  try {
    await navigator.clipboard.writeText(folder);
    setStatus('Path copied to clipboard.');
  } catch {
    setStatus('Copy failed (clipboard unavailable).', true);
  }
}
