/* ============================================================
   UniDL — Universal Downloader
   script.js
   ============================================================ */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ---------- mode switching (Catalogue / Resources / URL) ----------

const tabCatalogue   = $('#tabCatalogue');
const tabResources   = $('#tabResources');
const tabUrl         = $('#tabUrl');
const catalogueMode  = $('#catalogueMode');
const resourcesMode  = $('#resourcesMode');
const urlMode        = $('#urlMode');

const ALL_MODES = ['catalogue', 'resources', 'url'];

function switchMode(mode) {
  tabCatalogue.classList.toggle('active', mode === 'catalogue');
  tabResources.classList.toggle('active', mode === 'resources');
  tabUrl.classList.toggle('active', mode === 'url');
  catalogueMode.classList.toggle('hidden', mode !== 'catalogue');
  resourcesMode.classList.toggle('hidden', mode !== 'resources');
  urlMode.classList.toggle('hidden', mode !== 'url');
  localStorage.setItem('unidl-mode', mode);
}

tabCatalogue.addEventListener('click', () => switchMode('catalogue'));
tabResources.addEventListener('click', () => switchMode('resources'));
tabUrl.addEventListener('click', () => switchMode('url'));

// Restore last mode
const _savedMode = localStorage.getItem('unidl-mode') || 'catalogue';
switchMode(ALL_MODES.includes(_savedMode) ? _savedMode : 'catalogue');


// ---------- catalogue ----------

let catalogueData = null;          // raw JSON from /api/catalogue
let activeDeptId    = null;        // department id currently open
let activeSubjectId = null;        // subject chip selected
const STORAGE_DEPT_KEY = 'unidl-last-dept';
const STORAGE_SUB_KEY  = 'unidl-last-subject';

const catGrid      = $('#catalogueGrid');
const catSearch    = $('#catSearch');
const catClearBtn  = $('#catClearBtn');
const catLoadingBox = $('#catLoadingBox');
const catErrorBox  = $('#catErrorBox');

function catSiteBadgeClass(site) {
  const s = (site || '').toLowerCase().replace(/\s+/g, ' ');
  const map = {
    'nptel': 'site-nptel',
    'mit ocw': 'site-mit ocw',
    'freecodecamp': 'site-freecodecamp',
    'khan academy': 'site-khan academy',
    'youtube': 'site-youtube',
  };
  return map[s] || 'site-default';
}

function renderCatalogue(data) {
  catGrid.innerHTML = '';
  if (!data || !data.departments || !data.departments.length) {
    catGrid.innerHTML = '<p class="cat-no-results">No catalogue data found.</p>';
    return;
  }

  const savedDept = localStorage.getItem(STORAGE_DEPT_KEY);
  const savedSub  = localStorage.getItem(STORAGE_SUB_KEY);

  data.departments.forEach(dept => {
    const section = document.createElement('div');
    section.className = 'dept-section';
    section.dataset.deptId = dept.id;

    section.innerHTML = `
      <div class="dept-header">
        <span class="dept-icon">${dept.icon || '📁'}</span>
        <span class="dept-name">${escapeHtml(dept.name)}</span>
        <span class="dept-count">${dept.subjects.length} subjects</span>
        <span class="dept-chevron">▶</span>
      </div>
      <div class="dept-body">
        <div class="subject-chips"></div>
        <div class="playlist-cards"></div>
      </div>
    `;

    const header = section.querySelector('.dept-header');
    const chipsEl = section.querySelector('.subject-chips');
    const cardsEl = section.querySelector('.playlist-cards');

    // Build subject chips
    dept.subjects.forEach(subject => {
      const chip = document.createElement('button');
      chip.className = 'subject-chip';
      chip.textContent = `${subject.icon || ''} ${subject.name}`;
      chip.dataset.subjectId = subject.id;
      chip.addEventListener('click', () => {
        // deactivate other chips in same dept
        chipsEl.querySelectorAll('.subject-chip').forEach(c => c.classList.remove('active'));
        chip.classList.add('active');
        activeSubjectId = subject.id;
        localStorage.setItem(STORAGE_SUB_KEY, subject.id);
        renderPlaylistCards(cardsEl, subject, dept.name);
      });
      chipsEl.appendChild(chip);
    });

    // Toggle open/close
    header.addEventListener('click', () => {
      const isOpen = section.classList.contains('open');
      // close all sections
      $$('.dept-section').forEach(s => s.classList.remove('open'));
      if (!isOpen) {
        section.classList.add('open');
        activeDeptId = dept.id;
        localStorage.setItem(STORAGE_DEPT_KEY, dept.id);
        // auto-select first subject if none selected
        const firstChip = chipsEl.querySelector('.subject-chip');
        if (firstChip && !chipsEl.querySelector('.subject-chip.active')) {
          firstChip.click();
        }
      } else {
        activeDeptId = null;
      }
    });

    catGrid.appendChild(section);

    // Restore saved state
    if (dept.id === savedDept) {
      section.classList.add('open');
      activeDeptId = dept.id;
      dept.subjects.forEach(subject => {
        if (subject.id === savedSub) {
          const chip = chipsEl.querySelector(`[data-subject-id="${subject.id}"]`);
          if (chip) chip.click();
        }
      });
      // fallback: first subject
      if (!chipsEl.querySelector('.subject-chip.active')) {
        const firstChip = chipsEl.querySelector('.subject-chip');
        if (firstChip) firstChip.click();
      }
    }
  });

  // If nothing was restored, open first dept
  if (!$('.dept-section.open')) {
    const first = $('.dept-section');
    if (first) {
      const firstHeader = first.querySelector('.dept-header');
      if (firstHeader) firstHeader.click();
    }
  }
}

function renderPlaylistCards(container, subject, deptName) {
  container.innerHTML = '';
  if (!subject.playlists || !subject.playlists.length) {
    container.innerHTML = '<p class="cat-no-results">No playlists for this subject yet.</p>';
    return;
  }
  const q = catSearch.value.trim().toLowerCase();

  subject.playlists.forEach(pl => {
    const card = document.createElement('div');
    card.className = 'playlist-card';
    card.dataset.searchText = `${pl.title} ${subject.name} ${deptName} ${pl.uploader} ${pl.site}`.toLowerCase();

    const badgeClass = catSiteBadgeClass(pl.site);

    card.innerHTML = `
      <div class="card-top">
        <span class="card-site-badge ${badgeClass}">${escapeHtml(pl.site)}</span>
        <span class="card-title">${escapeHtml(pl.title)}</span>
      </div>
      <div class="card-uploader">📡 ${escapeHtml(pl.uploader)}</div>
      <div class="card-desc">${escapeHtml(pl.description)}</div>
      <div class="card-actions">
        <button class="btn btn-accent card-load">▶ Load &amp; Preview</button>
        <button class="btn card-dl-video">⬇️ Video+Audio</button>
        <button class="btn card-dl-audio">🎵 Audio MP3</button>
      </div>
    `;

    // Filter by current search query
    if (q && !card.dataset.searchText.includes(q)) {
      card.classList.add('hidden-search');
    }

    card.querySelector('.card-load').addEventListener('click', () => {
      loadCataloguePlaylist(pl.url, subject.name, pl.title, false, false);
    });
    card.querySelector('.card-dl-video').addEventListener('click', () => {
      loadCataloguePlaylist(pl.url, subject.name, pl.title, false, false, true);
    });
    card.querySelector('.card-dl-audio').addEventListener('click', () => {
      loadCataloguePlaylist(pl.url, subject.name, pl.title, true, false, true);
    });

    container.appendChild(card);
  });

  // Show no-results message if all hidden
  if (q && !container.querySelector('.playlist-card:not(.hidden-search)')) {
    const msg = document.createElement('p');
    msg.className = 'cat-no-results';
    msg.textContent = `No playlists match "${q}" in this subject.`;
    container.appendChild(msg);
  }
}

async function loadCataloguePlaylist(url, subjectName, playlistName, mp3, subtitles, directDownload = false) {
  // Switch to URL mode so user can see the playlist / download progress
  switchMode('url');
  clearError();

  const loadingBox = $('#loadingBox');
  const analyzeBtn = $('#analyzeBtn');
  const playlistSection = $('#playlistSection');
  const videoSection = $('#videoSection');

  playlistSection.classList.add('hidden');
  videoSection.classList.add('hidden');
  loadingBox.classList.remove('hidden');
  if (analyzeBtn) analyzeBtn.disabled = true;

  try {
    const res = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Something went wrong.');

    if (directDownload) {
      // Kick off download immediately without showing the playlist view
      const fmt = mp3 ? 'bestaudio' : 'bv*+ba/b';
      startDownload({
        url,
        format: fmt,
        mp3,
        playlist: true,
        label: playlistName,
        subject: subjectName,
        playlistName,
        subtitles: $('#dlSubtitles') ? $('#dlSubtitles').checked : false,
      });
    } else if (data.type === 'playlist') {
      renderPlaylist(data, subjectName, playlistName);
    } else {
      currentVideo = data;
      currentPlaylistUrl = null;
      renderVideo(data, false);
    }
  } catch (e) {
    showError(e.message);
  } finally {
    loadingBox.classList.add('hidden');
    if (analyzeBtn) analyzeBtn.disabled = false;
  }
}

// Catalogue search
catSearch.addEventListener('input', () => {
  const q = catSearch.value.trim().toLowerCase();
  catClearBtn.classList.toggle('hidden', !q);
  applySearchFilter(q);
});
catClearBtn.addEventListener('click', () => {
  catSearch.value = '';
  catClearBtn.classList.add('hidden');
  applySearchFilter('');
});

function applySearchFilter(q) {
  $$('.playlist-card').forEach(card => {
    const text = card.dataset.searchText || '';
    card.classList.toggle('hidden-search', !!(q && !text.includes(q)));
  });
  // Update no-results messages per cards container
  $$('.playlist-cards').forEach(container => {
    const existing = container.querySelector('.cat-no-results');
    const hasVisible = !!container.querySelector('.playlist-card:not(.hidden-search)');
    if (!hasVisible && q) {
      if (!existing) {
        const msg = document.createElement('p');
        msg.className = 'cat-no-results';
        msg.textContent = `No playlists match "${q}" here.`;
        container.appendChild(msg);
      }
    } else if (existing) {
      existing.remove();
    }
  });
}

async function fetchCatalogue() {
  catLoadingBox.classList.remove('hidden');
  catErrorBox.classList.add('hidden');
  try {
    const res = await fetch('/api/catalogue');
    const data = await res.json();
    if (!res.ok) throw new Error(data._error || 'Failed to load catalogue.');
    catalogueData = data;
    renderCatalogue(data);
  } catch (e) {
    catErrorBox.textContent = `Catalogue load failed: ${e.message}`;
    catErrorBox.classList.remove('hidden');
  } finally {
    catLoadingBox.classList.add('hidden');
  }
}

fetchCatalogue();

// ---------- URL mode ----------

const urlInput      = $('#urlInput');
const analyzeBtn    = $('#analyzeBtn');
const errorBox      = $('#errorBox');
const loadingBox    = $('#loadingBox');
const playlistSection = $('#playlistSection');
const videoSection  = $('#videoSection');
const outDirInput   = $('#outDir');

let currentVideo        = null;
let currentPlaylistUrl  = null;
let currentSubjectName  = null;
let currentPlaylistName = null;
let activeTab           = 'combined';

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove('hidden');
}
function clearError() {
  errorBox.classList.add('hidden');
  errorBox.textContent = '';
}

async function analyze() {
  const url = urlInput.value.trim();
  if (!url) { showError('Paste a URL first.'); return; }
  clearError();
  playlistSection.classList.add('hidden');
  videoSection.classList.add('hidden');
  loadingBox.classList.remove('hidden');
  analyzeBtn.disabled = true;

  // Reset catalogue context when manually entering a URL
  currentSubjectName  = null;
  currentPlaylistName = null;

  try {
    const res = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Something went wrong.');

    if (data.type === 'playlist') {
      renderPlaylist(data, null, null);
    } else {
      currentVideo = data;
      currentPlaylistUrl = null;
      renderVideo(data, false);
    }
  } catch (e) {
    showError(e.message);
  } finally {
    loadingBox.classList.add('hidden');
    analyzeBtn.disabled = false;
  }
}

function renderPlaylist(data, subjectName, playlistName) {
  currentPlaylistUrl  = data.playlist_url;
  currentSubjectName  = subjectName;
  currentPlaylistName = playlistName || data.playlist_title;

  $('#playlistTitle').textContent = data.playlist_title;
  $('#playlistCount').textContent = `${data.count} videos`;

  const wrap = $('#playlistItems');
  wrap.innerHTML = '';
  data.items.forEach((item, i) => {
    const div = document.createElement('div');
    div.className = 'pl-item';
    div.innerHTML = `
      <span class="pl-idx">${i + 1}.</span>
      <span class="pl-title">${escapeHtml(item.title || item.id)}</span>
      <span class="pl-dur">${item.duration || ''}</span>
    `;
    div.addEventListener('click', () => loadPlaylistVideo(item.url));
    wrap.appendChild(div);
  });

  playlistSection.classList.remove('hidden');
  videoSection.classList.add('hidden');

  // Wire quick-download buttons for the whole playlist
  playlistSection.querySelectorAll('.quick-row .btn').forEach((btn) => {
    btn.onclick = () => startDownload({
      url: data.playlist_url,
      format: btn.dataset.preset,
      mp3: btn.dataset.mp3 === '1',
      playlist: true,
      label: data.playlist_title,
      subject: currentSubjectName,
      playlistName: currentPlaylistName,
      subtitles: $('#dlSubtitles').checked,
    });
  });
}

async function loadPlaylistVideo(videoUrl) {
  clearError();
  loadingBox.classList.remove('hidden');
  try {
    const res = await fetch('/api/video_formats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: videoUrl }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not load that video.');
    currentVideo = data;
    renderVideo(data, true);
  } catch (e) {
    showError(e.message);
  } finally {
    loadingBox.classList.add('hidden');
  }
}

function renderVideo(data, cameFromPlaylist) {
  $('#videoThumb').src = data.thumbnail || '';
  $('#videoTitle').textContent = data.title || '(untitled)';
  $('#videoUploader').textContent = data.uploader || '';
  $('#videoDuration').textContent = data.duration ? `· ${data.duration}` : '';

  const backBtn = $('#backToPlaylist');
  if (cameFromPlaylist) {
    backBtn.classList.remove('hidden');
    backBtn.onclick = () => {
      videoSection.classList.add('hidden');
      playlistSection.classList.remove('hidden');
    };
  } else {
    backBtn.classList.add('hidden');
  }

  videoSection.querySelectorAll('.quick-row .btn').forEach((btn) => {
    btn.onclick = () => startDownload({
      url: data.webpage_url,
      format: btn.dataset.preset,
      mp3: btn.dataset.mp3 === '1',
      playlist: false,
      label: data.title,
      subject: null,
      playlistName: null,
      subtitles: false,
    });
  });

  const comboVideo = $('#comboVideo');
  const comboAudio = $('#comboAudio');
  comboVideo.innerHTML = '<option value="">— video-only format —</option>' +
    data.video_only.map(f => `<option value="${f.format_id}">${formatLabel(f, 'v')}</option>`).join('');
  comboAudio.innerHTML = '<option value="">— audio-only format —</option>' +
    data.audio_only.map(f => `<option value="${f.format_id}">${formatLabel(f, 'a')}</option>`).join('');
  updateComboBtn();
  comboVideo.onchange = updateComboBtn;
  comboAudio.onchange = updateComboBtn;
  $('#comboBtn').onclick = () => {
    const v = comboVideo.value, a = comboAudio.value;
    if (!v || !a) return;
    const vFmt = data.video_only.find(x => x.format_id === v);
    startDownload({
      url: data.webpage_url, format: `${v}+${a}`, mp3: false, playlist: false,
      label: data.title, mergeFormat: vFmt ? vFmt.ext : 'mp4',
    });
  };

  activeTab = data.combined.length ? 'combined' : (data.video_only.length ? 'video_only' : 'audio_only');
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === activeTab));
  renderFormatTable(data);

  videoSection.classList.remove('hidden');
}

function formatLabel(f, kind) {
  if (kind === 'v') {
    return `${f.format_id} · ${f.resolution || '?'} ${f.fps ? f.fps + 'fps' : ''} · ${f.ext} ${f.filesize ? '· ' + f.filesize : ''}`;
  }
  return `${f.format_id} · ${f.abr ? Math.round(f.abr) + 'kbps' : ''} · ${f.ext} ${f.filesize ? '· ' + f.filesize : ''}`;
}

function updateComboBtn() {
  const v = $('#comboVideo').value, a = $('#comboAudio').value;
  $('#comboBtn').disabled = !(v && a);
}

$$('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    activeTab = tab.dataset.tab;
    $$('.tab').forEach(t => t.classList.toggle('active', t === tab));
    renderFormatTable(currentVideo);
  });
});

const EMPTY_TAB_MESSAGES = {
  combined: "No combined or pairable formats found — check video-only / audio-only tabs.",
  video_only: "No video-only formats found for this video.",
  audio_only: "No audio-only formats found for this video.",
};

function renderFormatTable(data) {
  const rows = data[activeTab] || [];
  const body = $('#formatBody');
  body.innerHTML = '';
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="9" class="dim empty-tab-msg">${EMPTY_TAB_MESSAGES[activeTab] || 'No formats.'}</td></tr>`;
    return;
  }
  rows.forEach(f => {
    const tr = document.createElement('tr');
    const resOrAbr = activeTab === 'audio_only' ? (f.abr ? `${Math.round(f.abr)}kbps` : '—') : (f.resolution || '—');
    const codec = [
      f.vcodec ? `<span class="codec-v">${f.vcodec}</span>` : '',
      f.acodec ? `<span class="codec-a">${f.acodec}</span>` : '',
    ].filter(Boolean).join(' / ');
    tr.innerHTML = `
      <td>${f.format_id}</td>
      <td>${f.ext}</td>
      <td>${resOrAbr}</td>
      <td>${f.fps || '—'}</td>
      <td>${codec || '—'}</td>
      <td>${f.tbr ? Math.round(f.tbr) + 'kbps' : '—'}</td>
      <td>${f.filesize || '—'}</td>
      <td class="dim">${f.note || ''}</td>
      <td><button class="row-dl-btn">get</button></td>
    `;
    tr.querySelector('.row-dl-btn').onclick = () => startDownload({
      url: data.webpage_url,
      format: f.format_id,
      mp3: false,
      playlist: false,
      label: data.title,
      mergeFormat: f.ext,
    });
    body.appendChild(tr);
  });
}

analyzeBtn.addEventListener('click', analyze);
urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') analyze(); });

// ---------- downloads ----------

async function startDownload({ url, format, mp3, playlist, label, mergeFormat, subject, playlistName, subtitles }) {
  clearError();
  const out_dir = outDirInput.value.trim();
  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        format,
        mp3: !!mp3,
        playlist: !!playlist,
        out_dir,
        merge_format: mergeFormat,
        subject: subject || null,
        playlist_name: playlistName || null,
        subtitles: !!subtitles,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Could not start download.');
    addJobCard(data.job_id, label, format, subject);
    pollJob(data.job_id);
  } catch (e) {
    showError(e.message);
  }
}

function addJobCard(jobId, label, format, subjectName) {
  const list = $('#jobsList');
  const empty = list.querySelector('.empty-state');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = 'job';
  div.id = `job-${jobId}`;
  div.innerHTML = `
    <div class="job-top">
      <div>
        <div class="job-name">${escapeHtml(label || 'download')} <span class="dim">(${format})</span></div>
        ${subjectName ? `<div class="job-subject">📂 ${escapeHtml(subjectName)}</div>` : ''}
      </div>
      <span class="job-controls">
        <button class="job-btn job-pause">⏸ pause</button>
        <button class="job-btn job-resume hidden">▶ resume</button>
        <button class="job-btn job-cancel">✖ cancel</button>
        <button class="job-btn job-remove hidden" title="Remove from list">🗑 remove</button>
      </span>
      <span class="job-status queued">🕓 queued</span>
    </div>
    <div class="bar-track"><div class="bar-fill"></div></div>
    <div class="job-sub"><span class="job-file dim"></span><span class="job-speed dim"></span></div>
  `;
  list.prepend(div);

  bindClick(div, '.job-pause',  () => jobControl(jobId, 'pause'));
  bindClick(div, '.job-resume', () => jobControl(jobId, 'resume'));
  bindClick(div, '.job-cancel', () => jobControl(jobId, 'cancel'));
  bindClick(div, '.job-remove', () => removeJob(jobId));
}

function bindClick(root, selector, handler) {
  const el = root.querySelector(selector);
  if (el) {
    el.addEventListener('click', handler);
  } else {
    console.warn(`UniDL: expected "${selector}" inside a job card but didn't find it.`);
  }
}

function removeJob(jobId) {
  const card = $(`#job-${jobId}`);
  if (card) {
    card.classList.add('removing');
    setTimeout(() => {
      card.remove();
      const list = $('#jobsList');
      if (!list.querySelector('.job')) {
        list.innerHTML = `<div class="empty-state dim">nothing downloading yet — browse the catalogue or paste a URL above</div>`;
      }
    }, 200);
  }
  fetch(`/api/job/${jobId}`, { method: 'DELETE' }).catch(() => {});
}

async function jobControl(jobId, action) {
  try {
    const res = await fetch(`/api/job/${jobId}/${action}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `could not ${action}`);
    if (action === 'resume') pollJob(jobId);
  } catch (e) {
    showError(e.message);
  }
}

const ACTIVE_STATES   = ['queued', 'downloading', 'merging', 'retrying'];
const TERMINAL_STATES = ['finished', 'error', 'cancelled'];

function updateJobControls(card, status) {
  const pauseBtn  = card.querySelector('.job-pause');
  const resumeBtn = card.querySelector('.job-resume');
  const cancelBtn = card.querySelector('.job-cancel');
  const removeBtn = card.querySelector('.job-remove');

  if (pauseBtn)  pauseBtn.classList.toggle('hidden',  !ACTIVE_STATES.includes(status));
  if (resumeBtn) resumeBtn.classList.toggle('hidden', status !== 'paused');
  if (cancelBtn) cancelBtn.classList.toggle('hidden', TERMINAL_STATES.includes(status));
  if (removeBtn) removeBtn.classList.toggle('hidden', !(TERMINAL_STATES.includes(status) || status === 'paused'));
}

function pollJob(jobId) {
  const card = $(`#job-${jobId}`);
  if (!card) return;
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`/api/progress/${jobId}`);
      const job = await res.json();
      if (!res.ok) { clearInterval(interval); return; }

      const statusEl = card.querySelector('.job-status');
      const STATUS_ICONS = {
        queued: '🕓', downloading: '⬇️', merging: '🔀', retrying: '🔁',
        paused: '⏸', finished: '✅', error: '❌', cancelled: '🚫',
      };
      statusEl.textContent = `${STATUS_ICONS[job.status] || '•'} ${job.status}`;
      statusEl.className = `job-status ${job.status}`;
      card.querySelector('.bar-fill').style.width = `${job.percent || 0}%`;
      card.querySelector('.job-file').textContent = job.filename || '';
      card.querySelector('.job-speed').textContent =
        job.status === 'downloading' && job.speed ? `${job.speed}${job.eta ? ' · ETA ' + job.eta : ''}` : '';

      updateJobControls(card, job.status);

      if (['finished', 'error', 'cancelled', 'paused'].includes(job.status)) {
        clearInterval(interval);
        if (job.status === 'error') {
          card.querySelector('.job-file').textContent = (job.log || []).slice(-1)[0] || 'failed';
        }
      }
    } catch (e) {
      console.error('UniDL: lost connection to /api/progress poll:', e);
      clearInterval(interval);
    }
  }, 1000);
}

$('#openFolderBtn').addEventListener('click', async () => {
  await fetch('/api/open_folder', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: outDirInput.value.trim() }),
  });
});

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

// ---------- theme ----------
(function initTheme() {
  const STORAGE_KEY = 'unidl-theme-mode';
  const toggle = $('#themeToggle');

  function apply(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    toggle.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
  }
  function setMode(mode) {
    localStorage.setItem(STORAGE_KEY, mode);
    apply(mode);
  }

  apply(localStorage.getItem(STORAGE_KEY) || 'dark');
  toggle.querySelectorAll('button').forEach(btn => {
    btn.addEventListener('click', () => setMode(btn.dataset.mode));
  });
})();

// ============================================================
// RESOURCES TAB
// ============================================================

(function initResources() {
  const resSearch     = $('#resSearch');
  const resSource     = $('#resSource');
  const resSearchBtn  = $('#resSearchBtn');
  const resScholarBtn = $('#resScholarBtn');
  const resLoadingBox = $('#resLoadingBox');
  const resErrorBox   = $('#resErrorBox');
  const resResultsCount = $('#resResultsCount');
  const resResults    = $('#resResults');
  const docUrlInput   = $('#docUrlInput');
  const docUrlIcon    = $('#docUrlIcon');
  const docDownloadBtn = $('#docDownloadBtn');
  const docUrlHint    = $('#docUrlHint');
  const scribdWarning = $('#scribdWarning');

  // ---- URL type detection ----
  function detectDocType(url) {
    const u = url.toLowerCase();
    if (u.includes('slideshare.net')) return 'slideshare';
    if (u.includes('scribd.com'))     return 'scribd';
    if (/\.(pdf|ppt|pptx|doc|docx|epub)(\?|$)/.test(u)) return 'direct';
    if (u.startsWith('http'))         return 'direct';
    return null;
  }

  const TYPE_ICONS = { slideshare: '🎞', scribd: '📜', direct: '🔗' };
  const TYPE_HINTS = {
    slideshare: 'SlideShare detected — will download slides via yt-dlp.',
    scribd:     'Scribd detected — will use headless Chrome (Google Chrome must be installed).',
    direct:     'Direct PDF/PPT link — will be downloaded via HTTP.',
    null:       'Paste a SlideShare, Scribd, or any direct .pdf / .pptx link — type is detected automatically.',
  };

  docUrlInput.addEventListener('input', () => {
    const url = docUrlInput.value.trim();
    const type = detectDocType(url);
    docUrlIcon.textContent = TYPE_ICONS[type] || '📎';
    docUrlHint.textContent = TYPE_HINTS[type] || TYPE_HINTS[null];
    scribdWarning.classList.toggle('hidden', type !== 'scribd');
  });

  // ---- Doc download dispatcher ----
  docDownloadBtn.addEventListener('click', async () => {
    const url = docUrlInput.value.trim();
    if (!url) { showResError('Paste a URL first.'); return; }
    const type = detectDocType(url);
    clearResError();

    if (type === 'scribd') {
      await downloadScribd(url);
    } else if (type === 'slideshare') {
      // SlideShare — use our custom scraper (yt-dlp extractor is broken)
      const label = url.split('/').pop().split('?')[0] || 'slides';
      await downloadSlideshare(url, label);
    } else {
      // Direct PDF/PPT
      const label = url.split('/').pop().split('?')[0] || 'document';
      await downloadDirectResource(url, label, 'Resources');
    }
  });

  docUrlInput.addEventListener('keydown', e => { if (e.key === 'Enter') docDownloadBtn.click(); });

  // ---- Search ----
  resSearchBtn.addEventListener('click', doSearch);
  resSearch.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

  async function doSearch() {
    const q = resSearch.value.trim();
    if (!q) return;

    // Update Google Scholar link
    resScholarBtn.href = `https://scholar.google.com/scholar?q=${encodeURIComponent(q)}`;

    resLoadingBox.classList.remove('hidden');
    resErrorBox.classList.add('hidden');
    resResults.innerHTML = '';
    resResultsCount.classList.add('hidden');

    try {
      const src = resSource.value;
      const res = await fetch(`/api/search_resources?q=${encodeURIComponent(q)}&source=${src}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Search failed');
      renderResResults(data.results, q);
      resResultsCount.textContent = `${data.count} result${data.count !== 1 ? 's' : ''} for "${q}"`;
      resResultsCount.classList.remove('hidden');
    } catch (e) {
      showResError(e.message);
    } finally {
      resLoadingBox.classList.add('hidden');
    }
  }

  function renderResResults(results, query) {
    resResults.innerHTML = '';
    if (!results || !results.length) {
      resResults.innerHTML = `<p class="cat-no-results">No results found for "${escapeHtml(query)}". Try a different search term or source.</p>`;
      return;
    }
    results.forEach(r => {
      const card = document.createElement('div');
      card.className = 'res-card';

      const sourceClass = r.source === 'Open Library' ? 'res-source-openlibrary' : 'res-source-archive';
      const sourceLabel = r.source || 'Unknown';
      const typeIcon = r.type === 'book' ? '📗' : r.type === 'pdf' ? '📄' : r.type === 'ppt' || r.type === 'pptx' ? '📊' : '📑';

      // Cover
      let coverHtml = '';
      if (r.cover_url) {
        coverHtml = `<div class="res-card-cover"><img src="${escapeHtml(r.cover_url)}" alt="" loading="lazy" onerror="this.parentNode.textContent='${typeIcon}'"></div>`;
      } else {
        coverHtml = `<div class="res-card-cover">${typeIcon}</div>`;
      }

      // Formats
      let fmtsHtml = '';
      if (r.formats && r.formats.length) {
        fmtsHtml = `<div class="res-card-formats">${r.formats.map(f => `<span class="res-fmt-badge">${escapeHtml(f)}</span>`).join('')}</div>`;
      }

      // Actions
      const openBtn = r.open_url
        ? `<a href="${escapeHtml(r.open_url)}" target="_blank" rel="noopener" class="btn btn-ghost">🔗 Open</a>`
        : '';
      const dlBtn = r.download_url
        ? `<button class="btn btn-accent res-dl-btn">⬇️ Download ${(r.type || 'PDF').toUpperCase()}</button>`
        : '';
      const scholarBtn = `<a href="https://scholar.google.com/scholar?q=${encodeURIComponent(r.title)}" target="_blank" rel="noopener" class="btn btn-ghost" title="Search on Google Scholar">🎓</a>`;

      card.innerHTML = `
        ${coverHtml}
        <div class="res-card-body">
          <span class="res-card-source ${sourceClass}">${escapeHtml(sourceLabel)}</span>
          <div class="res-card-title">${escapeHtml(r.title)}</div>
          ${r.author ? `<div class="res-card-author">✍️ ${escapeHtml(r.author)}${r.year ? ` · ${r.year}` : ''}</div>` : ''}
          ${fmtsHtml}
          <div class="res-card-actions">
            ${dlBtn}${openBtn}${scholarBtn}
          </div>
        </div>
      `;

      if (r.download_url) {
        card.querySelector('.res-dl-btn').addEventListener('click', () => {
          downloadDirectResource(r.download_url, r.title, query);
        });
      }

      resResults.appendChild(card);
    });
  }

  // ---- Direct resource download ----
  async function downloadDirectResource(url, label, topic) {
    clearResError();
    try {
      const res = await fetch('/api/download_resource', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, label, topic: topic || 'Resources' }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start download');
      addJobCard(data.job_id, label || 'document', 'pdf/direct', null);
      pollJob(data.job_id);
    } catch (e) {
      showResError(e.message);
    }
  }

  // ---- SlideShare download ----
  async function downloadSlideshare(url, label) {
    clearResError();
    try {
      const res = await fetch('/api/slideshare_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, label }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start SlideShare download');
      addJobCard(data.job_id, label || 'slideshare', 'slideshare→pdf', null);
      pollJob(data.job_id);
    } catch (e) {
      showResError(e.message);
    }
  }

  // ---- Scribd download ----
  async function downloadScribd(url) {
    clearResError();
    const label = url.split('/').pop().split('?')[0] || 'scribd-doc';
    try {
      const res = await fetch('/api/scribd_download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, label }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start Scribd download');
      addJobCard(data.job_id, label, 'scribd→pdf', null);
      pollJob(data.job_id);
    } catch (e) {
      showResError(e.message);
    }
  }

  function showResError(msg) {
    resErrorBox.textContent = msg;
    resErrorBox.classList.remove('hidden');
  }
  function clearResError() {
    resErrorBox.classList.add('hidden');
    resErrorBox.textContent = '';
  }
})();
