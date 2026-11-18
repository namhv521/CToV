'use strict';

const $ = id => document.getElementById(id);

const ALLOWED_HOSTS = new Set([
  'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
  'threads.net', 'www.threads.net', 'threads.com', 'www.threads.com',
]);

const VIEW_META = {
  studio: ['Sản xuất hàng loạt', 'Nạp danh sách URLs → Tự động chụp bình luận thật, chia phần & xuất MP4'],
  history: ['Kho video & Lịch sử', 'Quản lý toàn bộ bài đã crawl theo ngày, xem trước MP4, mở thư mục và render lại'],
  library: ['Thư viện & Thư mục', 'Chọn thư mục bất kỳ trên máy cho Video nền, Video Meme, Ảnh Meme và Tiếng Meme'],
  voices: ['Giọng đọc ElevenLabs', 'Cấu hình API Key và danh sách Voice ID phối ngẫu nhiên cho toàn bộ lô video'],
};

let currentView = 'studio';
let ffmpegReady = null;
let library = [];
let mediaDiag = {
  background_count: 0,
  meme_video_count: 0,
  meme_image_count: 0,
  meme_sound_count: 0,
  paired_meme_count: 0,
  random_paired_count: 0,
  missing_sounds: [],
  unpaired_images: [],
  folders: {},
};
let narrationSettings = { key: false, voice: '', voices: ['', '', ''], model: 'eleven_v3' };
let preset = defaultPreset();

let batches = [];
let selectedBatchId = '';
let currentBatch = null;
let batchFilter = 'all';

let crawlDays = [];
let selectedDay = '';
let libFilter = 'all';

let pollTimer = null;
let presetSaveTimer = null;
let previewTimer = null;
let noticeTimer = null;
let cardPreviewUrl = null;
let voicePreviewUrl = null;
let previewSeq = 0;

function defaultPreset() {
  return {
    limit: 30,
    auto_render: true,
    options: {
      provider: 'elevenlabs',
      voice: '',
      elevenlabs_voices: [''],
      use_meme_video: false,
      use_meme_image: true,
      use_meme_sound: true,
      speed: 1.1,
      resolution: 720,
      background: '',
      default_meme: '',
      default_sound: '',
      credit: 'CRE: COMMENTCUT',
      card_y: 0.28,
      max_seconds: 120,
      split_mode: 'comments',
      video_count: 3,
      comments_per_video: 10,
      read_post: true,
      anonymous: false,
      meme_volume: 0.65,
    },
  };
}

function node(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

function compactPath(displayPath) {
  if (!displayPath) return '';
  if (displayPath.startsWith('data/')) return displayPath;
  const parts = displayPath.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return displayPath;
  return `${parts[0]}/…/${parts[parts.length - 1]}`;
}

function notice(text, error = false) {
  clearTimeout(noticeTimer);
  const box = $('notice');
  box.textContent = text;
  box.className = error ? 'toast error' : 'toast';
  box.hidden = false;
  noticeTimer = setTimeout(() => { box.hidden = true; }, error ? 12000 : 5500);
}

async function api(path, options = {}) {
  const r = await fetch(path, options);
  if (!r.ok) {
    let detail = `Lỗi HTTP ${r.status}`;
    try {
      const body = await r.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return r;
}

const postJson = async (path, body) =>
  (await api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).json();

async function busy(button, task, busyLabel = 'Đang xử lý…') {
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  if (busyLabel) button.textContent = busyLabel;
  try {
    return await task();
  } catch (err) {
    notice(err.message || String(err), true);
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    button.textContent = original;
    refreshPreflightAndCTA();
  }
}

/* NAVIGATION */
function setView(view) {
  if (!VIEW_META[view]) return;
  currentView = view;
  document.querySelectorAll('.view-pane').forEach(el => {
    el.hidden = el.id !== 'view-' + view;
  });
  document.querySelectorAll('.nav-btn').forEach(btn => {
    const active = btn.dataset.view === view;
    btn.classList.toggle('active', active);
    if (active) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });
  const [title, sub] = VIEW_META[view];
  $('topbar-title').textContent = title;
  $('topbar-subtitle').textContent = sub;

  if (view === 'history') loadCrawlDays().catch(e => notice(e.message, true));
  if (view === 'library') loadAssets().catch(e => notice(e.message, true));
}

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => setView(btn.dataset.view));
});

/* FOLDER OPENER & NATIVE FOLDER PICKER */
async function openLocalFolder(target, projectId = null) {
  try {
    await postJson('/api/open-folder', { target, project_id: projectId });
  } catch (err) {
    notice(err.message, true);
  }
}

async function pickMediaFolder(kind, button) {
  await busy(button, async () => {
    const res = await postJson('/api/media-folders/pick', { kind });
    if (!res.picked) return;
    mediaDiag = res.media || mediaDiag;
    await loadAssets();
    const info = mediaDiag.folders?.[kind];
    notice(`Đã chọn thư mục: ${res.path} (${info ? info.count : 0} tệp hợp lệ).`);
  }, 'Đang chọn…');
}

async function resetMediaFolder(kind, button) {
  await busy(button, async () => {
    const diag = await postJson('/api/media-folders', { kind, path: '' });
    mediaDiag = diag || mediaDiag;
    await loadAssets();
    notice('Đã đặt lại về thư mục mặc định trong data.');
  }, 'Đang đặt lại…');
}

$('btn-open-output').addEventListener('click', () => openLocalFolder('output'));
document.querySelectorAll('[data-open-folder]').forEach(btn => {
  btn.addEventListener('click', () => openLocalFolder(btn.dataset.openFolder));
});
document.querySelectorAll('[data-pick-folder]').forEach(btn => {
  btn.addEventListener('click', () => pickMediaFolder(btn.dataset.pickFolder, btn));
});
document.querySelectorAll('[data-reset-folder]').forEach(btn => {
  btn.addEventListener('click', () => resetMediaFolder(btn.dataset.resetFolder, btn));
});

/* PLATFORM LOGIN */
for (const [id, platform] of [['btn-login-tiktok', 'tiktok'], ['btn-login-threads', 'threads']]) {
  $(id).addEventListener('click', () => busy($(id), async () => {
    const res = await postJson('/api/login/' + platform, {});
    notice(res.message);
  }));
}

/* URL PARSER & INPUT TOOLS */
function classifyUrlLine(raw) {
  const line = raw.trim();
  if (!line || line.startsWith('#')) return { kind: 'ignore' };
  try {
    const u = new URL(line);
    if (u.protocol !== 'https:' || !ALLOWED_HOSTS.has(u.hostname) || u.username || u.password || (u.port && u.port !== '443')) {
      return { kind: 'invalid', raw: line };
    }
    const platform = u.hostname.includes('tiktok') ? 'tiktok' : 'threads';
    return { kind: 'valid', url: line, platform };
  } catch {
    return { kind: 'invalid', raw: line };
  }
}

function analyzeUrlInput() {
  const lines = $('batch-urls').value.replace(/^\uFEFF/, '').split(/\r?\n/);
  const urls = [];
  const seen = new Set();
  let duplicates = 0;
  let invalid = 0;
  let tiktok = 0;
  let threads = 0;

  for (const raw of lines) {
    const res = classifyUrlLine(raw);
    if (res.kind === 'ignore') continue;
    if (res.kind === 'invalid') {
      invalid++;
      continue;
    }
    if (seen.has(res.url)) {
      duplicates++;
      continue;
    }
    seen.add(res.url);
    urls.push(res.url);
    if (res.platform === 'tiktok') tiktok++;
    else threads++;
  }
  return { urls, duplicates, invalid, tiktok, threads };
}

function updateUrlSummary() {
  const info = analyzeUrlInput();
  $('url-valid-badge').textContent = `${info.urls.length} URL`;
  if (!info.urls.length && !info.invalid) {
    $('url-parse-hint').textContent = 'Mỗi dòng 1 link HTTPS TikTok / Threads. Có thể kéo thả trực tiếp file .txt vào ô trên.';
  } else {
    const parts = [`Hợp lệ: ${info.urls.length} link`];
    if (info.urls.length) parts.push(`(${info.threads} Threads · ${info.tiktok} TikTok)`);
    if (info.duplicates) parts.push(`đã bỏ qua ${info.duplicates} link trùng`);
    if (info.invalid) parts.push(`${info.invalid} dòng sai định dạng`);
    $('url-parse-hint').textContent = parts.join(' · ');
  }
  refreshPreflightAndCTA();
}

$('batch-urls').addEventListener('input', updateUrlSummary);

$('btn-clean-urls').addEventListener('click', () => {
  const info = analyzeUrlInput();
  $('batch-urls').value = info.urls.join('\n');
  updateUrlSummary();
  notice(`Đã lọc sạch: giữ ${info.urls.length} URL hợp lệ.`);
});

$('btn-clear-urls').addEventListener('click', () => {
  $('batch-urls').value = '';
  updateUrlSummary();
});

async function importTxtFile(file) {
  if (!file) return;
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await (await api('/api/batch-crawl/parse', { method: 'POST', body: form })).json();
    const existing = analyzeUrlInput().urls;
    const merged = Array.from(new Set([...existing, ...res.urls]));
    $('batch-urls').value = merged.join('\n');
    updateUrlSummary();
    const invalidNote = res.invalid.length ? ` (${res.invalid.length} dòng lỗi đã bỏ qua)` : '';
    notice(`Đã nạp ${res.count} URL từ "${file.name}"${invalidNote}.`, !res.count);
  } catch (err) {
    notice(err.message, true);
  }
}

$('batch-txt-file').addEventListener('change', async () => {
  await importTxtFile($('batch-txt-file').files[0]);
  $('batch-txt-file').value = '';
});

$('batch-urls').addEventListener('dragover', e => {
  e.preventDefault();
  $('batch-urls').classList.add('drag-over');
});
$('batch-urls').addEventListener('dragleave', () => {
  $('batch-urls').classList.remove('drag-over');
});
$('batch-urls').addEventListener('drop', async e => {
  e.preventDefault();
  $('batch-urls').classList.remove('drag-over');
  const file = e.dataTransfer?.files?.[0];
  if (file) await importTxtFile(file);
});

/* PRESET CONTROLS & MEME RULES */
function readControlsIntoPreset() {
  const maxSec = Math.max(15, Math.min(600, Number($('opt-max-seconds').value) || 120));
  preset.limit = Math.max(1, Math.min(120, Number($('batch-limit').value) || 30));
  preset.auto_render = $('opt-auto-render').checked;
  preset.options = {
    ...preset.options,
    provider: 'elevenlabs',
    elevenlabs_voices: [...narrationSettings.voices],
    split_mode: $('batch-split-mode').value,
    comments_per_video: Math.max(1, Math.min(120, Number($('batch-cpv').value) || 10)),
    video_count: Math.max(1, Math.min(120, Number($('batch-vcount').value) || 3)),
    max_seconds: maxSec,
    background: $('opt-background').value,
    resolution: Number($('opt-resolution').value) || 720,
    speed: Number($('opt-speed').value) || 1.1,
    read_post: $('opt-read-post').checked,
    use_meme_video: $('opt-meme-video').checked,
    use_meme_image: $('opt-meme-image').checked,
    use_meme_sound: $('opt-meme-sound').checked,
    credit: $('opt-credit').value,
    card_y: Number($('opt-card-y').value) || 0.28,
    meme_volume: Number($('opt-meme-volume').value) ?? 0.65,
  };
  return preset;
}

function applyPresetToControls() {
  $('batch-limit').value = preset.limit;
  $('opt-auto-render').checked = preset.auto_render;
  const o = preset.options;
  $('batch-split-mode').value = o.split_mode || 'comments';
  $('batch-cpv').value = o.comments_per_video || 10;
  $('batch-vcount').value = o.video_count || 3;
  $('opt-max-seconds').value = o.max_seconds || 120;
  $('opt-max-seconds-quick').value = o.max_seconds || 120;
  $('opt-resolution').value = String(o.resolution || 720);
  $('opt-speed').value = String(o.speed || 1.1);
  $('opt-read-post').checked = o.read_post !== false;
  $('opt-meme-video').checked = !!o.use_meme_video;
  const imgOn = o.use_meme_image !== false;
  const sndOn = imgOn ? true : o.use_meme_sound !== false;
  $('opt-meme-image').checked = imgOn;
  $('opt-meme-sound').checked = sndOn;
  $('opt-credit').value = o.credit ?? 'CRE: COMMENTCUT';
  $('opt-card-y').value = o.card_y ?? 0.28;
  $('opt-meme-volume').value = o.meme_volume ?? 0.65;
  populateBackgroundSelect();
  updateSplitUI();
  updateMemeRuleHint();
}

function updateMemeRuleHint() {
  const mv = $('opt-meme-video').checked;
  const mi = $('opt-meme-image').checked;
  const ms = $('opt-meme-sound').checked;
  const hint = $('meme-rule-hint');
  if (mv && mi && ms) {
    hint.textContent = 'Đang chọn cả 3: lấy ngẫu nhiên xen kẽ giữa Video Meme và cặp Ảnh + Tiếng Meme.';
  } else if (mv && !mi && !ms) {
    hint.textContent = 'Chế độ Video Meme độc lập: lấy ngẫu nhiên clip + âm thanh gốc trong folder (không cần Ảnh & Tiếng).';
  } else if (!mv && mi && ms) {
    hint.textContent = 'Chế độ Ảnh + Tiếng Meme: ưu tiên ghép trùng tên file, nếu khác tên sẽ tự ghép ngẫu nhiên.';
  } else if (mv && !mi && ms) {
    hint.textContent = 'Đang trộn ngẫu nhiên giữa Video Meme và Tiếng Meme.';
  } else if (!mv && !mi && ms) {
    hint.textContent = 'Chỉ phát ngẫu nhiên Tiếng Meme trên nền video.';
  } else {
    hint.textContent = 'Đã tắt chèn Meme giữa các bình luận.';
  }
}

$('opt-meme-image').addEventListener('change', () => {
  if ($('opt-meme-image').checked && !$('opt-meme-sound').checked) {
    $('opt-meme-sound').checked = true;
    notice('Đã tự động bật Tiếng Meme đi kèm Ảnh Meme.');
  }
  updateMemeRuleHint();
  scheduleSavePreset();
});

$('opt-meme-sound').addEventListener('change', () => {
  if (!$('opt-meme-sound').checked && $('opt-meme-image').checked) {
    $('opt-meme-image').checked = false;
    notice('Đã tắt cùng Ảnh Meme (vì chọn Ảnh bắt buộc phải có Tiếng).');
  }
  updateMemeRuleHint();
  scheduleSavePreset();
});

$('opt-meme-video').addEventListener('change', () => {
  updateMemeRuleHint();
  scheduleSavePreset();
});

function updateSplitUI() {
  const mode = $('batch-split-mode').value;
  $('wrap-cpv').hidden = mode !== 'comments';
  $('wrap-vcount').hidden = mode !== 'even';
  $('wrap-duration-note').hidden = mode !== 'duration';

  $('val-card-y').textContent = Math.round((Number($('opt-card-y').value) || 0.28) * 100) + '%';
  $('val-meme-vol').textContent = Math.round((Number($('opt-meme-volume').value) ?? 0.65) * 100) + '%';

  const limit = Math.max(1, Math.min(120, Number($('batch-limit').value) || 30));
  const auto = $('opt-auto-render').checked;

  document.querySelectorAll('[data-limit-preset]').forEach(btn => {
    btn.classList.toggle('active', Number(btn.dataset.limitPreset) === limit);
  });
  const cpv = Math.max(1, Math.min(120, Number($('batch-cpv').value) || 10));
  document.querySelectorAll('[data-cpv-preset]').forEach(btn => {
    btn.classList.toggle('active', Number(btn.dataset.cpvPreset) === cpv);
  });

  if (!auto) {
    $('split-formula-hint').textContent = `Chỉ Crawl: mỗi URL chụp tối đa ${limit} cmt nhiều tim nhất và lưu vào Kho video & Lịch sử (chưa tự động dựng MP4).`;
  } else if (mode === 'comments') {
    const est = Math.ceil(limit / cpv);
    $('split-formula-hint').textContent = `Mỗi URL lấy tối đa ${limit} cmt → chia ${cpv} cmt/video (tối đa ${est} video MP4/URL, tự động ghép theo số thực tế).`;
  } else if (mode === 'even') {
    const vc = Math.max(1, Number($('batch-vcount').value) || 3);
    $('split-formula-hint').textContent = `Mỗi URL lấy tối đa ${limit} cmt → chia đều thành ${vc} video MP4 và tự động xuất file.`;
  } else {
    const maxS = Number($('opt-max-seconds').value) || 120;
    $('split-formula-hint').textContent = `Mỗi URL lấy tối đa ${limit} cmt → tự ngắt phần khi chạm ngưỡng ${maxS} giây/video.`;
  }
}

function scheduleSavePreset() {
  readControlsIntoPreset();
  updateSplitUI();
  refreshPreflightAndCTA();
  $('preset-save-hint').textContent = 'Đang lưu…';
  clearTimeout(presetSaveTimer);
  presetSaveTimer = setTimeout(async () => {
    try {
      await postJson('/api/preset', preset);
      $('preset-save-hint').textContent = 'Đã lưu cấu hình';
    } catch {
      $('preset-save-hint').textContent = 'Chưa lưu được';
    }
  }, 450);

  if ($('advanced-layout-details').open) {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updateMiniPreview, 400);
  }
}

for (const id of [
  'batch-limit', 'batch-split-mode', 'batch-cpv', 'batch-vcount',
  'opt-background', 'opt-resolution', 'opt-speed',
  'opt-auto-render', 'opt-read-post',
  'opt-credit', 'opt-card-y', 'opt-meme-volume', 'opt-max-seconds',
]) {
  $(id).addEventListener('input', () => {
    if (id === 'opt-max-seconds') $('opt-max-seconds-quick').value = $('opt-max-seconds').value;
    if (id === 'opt-background') updateBackgroundVideoPreview();
    scheduleSavePreset();
  });
  $(id).addEventListener('change', scheduleSavePreset);
}

$('opt-max-seconds-quick').addEventListener('input', () => {
  $('opt-max-seconds').value = $('opt-max-seconds-quick').value;
  scheduleSavePreset();
});

document.querySelectorAll('[data-limit-preset]').forEach(btn => {
  btn.addEventListener('click', () => {
    $('batch-limit').value = btn.dataset.limitPreset;
    scheduleSavePreset();
  });
});

document.querySelectorAll('[data-cpv-preset]').forEach(btn => {
  btn.addEventListener('click', () => {
    $('batch-split-mode').value = 'comments';
    $('batch-cpv').value = btn.dataset.cpvPreset;
    scheduleSavePreset();
  });
});

$('advanced-layout-details').addEventListener('toggle', () => {
  if ($('advanced-layout-details').open) {
    updateBackgroundVideoPreview();
    updateMiniPreview();
  }
});

/* MINI 9:16 LAYOUT PREVIEW */
function updateBackgroundVideoPreview() {
  const chosen = $('opt-background').value || library.find(a => a.kind === 'background')?.id;
  const video = $('background-preview');
  $('preview-empty-note').hidden = !!chosen;
  if (chosen) {
    const src = `/api/assets/${chosen}/file`;
    if (video.getAttribute('src') !== src) {
      video.src = src;
      video.play().catch(() => {});
    }
  } else {
    video.removeAttribute('src');
    video.load();
  }
}

async function updateMiniPreview() {
  if (!$('advanced-layout-details').open) return;
  const seq = ++previewSeq;
  readControlsIntoPreset();
  try {
    const r = await api('/api/card-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ options: preset.options, comments: [] }),
    });
    const blob = await r.blob();
    if (seq !== previewSeq) return;
    if (cardPreviewUrl) URL.revokeObjectURL(cardPreviewUrl);
    cardPreviewUrl = URL.createObjectURL(blob);
    const img = $('card-preview');
    img.src = cardPreviewUrl;
    img.hidden = false;
  } catch {
    if (seq === previewSeq) $('card-preview').hidden = true;
  }
}

/* SYSTEM DIAGNOSTICS, FOLDER BADGES & PREFLIGHT */
function updateFolderBadgesUI() {
  const folders = mediaDiag.folders || {};
  const defaults = {
    background: 'data/Vid_nen',
    meme_video: 'data/vid_meme',
    image: 'data/img_meme',
    sound: 'data/mp3_meme',
  };

  for (const kind of ['background', 'meme_video', 'image', 'sound']) {
    const info = folders[kind] || { display_path: defaults[kind], path: defaults[kind], exists: true, is_custom: false };
    const studioChip = $('studio-folder-' + kind);
    if (studioChip) {
      studioChip.textContent = compactPath(info.display_path);
      studioChip.title = info.path || info.display_path;
      studioChip.classList.toggle('missing', info.exists === false);
    }
    const libChip = $('lib-path-' + kind);
    if (libChip) {
      libChip.textContent = info.is_custom ? info.path : `Mặc định: ${info.display_path}`;
      libChip.title = info.path || info.display_path;
      libChip.classList.toggle('missing', info.exists === false);
    }
    const resetBtn = $('reset-folder-' + kind);
    if (resetBtn) {
      resetBtn.hidden = !info.is_custom;
    }
  }

  $('badge-count-meme_video').textContent = `${mediaDiag.meme_video_count || 0} video`;
  $('badge-count-image').textContent = `${mediaDiag.meme_image_count || 0} ảnh`;
  $('badge-count-sound').textContent = `${mediaDiag.meme_sound_count || 0} âm`;
}

function narrationIssue() {
  if (!narrationSettings.key) {
    return 'Chưa lưu API Key ElevenLabs → Bấm vào đây để thiết lập.';
  }
  const v = narrationSettings.voices;
  if ((v.length > 1 && !v.every(Boolean)) || (v.length === 1 && !v[0] && !narrationSettings.voice)) {
    return `Chưa nhập đủ ${v.length} Voice ID ElevenLabs → Bấm vào đây để điền.`;
  }
  return '';
}

function activeRunningBatch() {
  return batches.find(b => ['queued', 'running'].includes(b.status)) || null;
}

function computePreflightIssues() {
  const issues = [];
  if (ffmpegReady === false) {
    issues.push({ text: 'Chưa tìm thấy FFmpeg trên hệ thống. Hãy cài FFmpeg trước khi render.', view: null });
  }
  if ($('opt-auto-render').checked) {
    const vIssue = narrationIssue();
    if (vIssue) {
      issues.push({ text: vIssue, view: 'voices', focus: narrationSettings.key ? 'eleven-voice-1' : 'elevenlabs_key' });
    }
    const hasBg = $('opt-background').value
      ? library.some(a => a.id === $('opt-background').value)
      : mediaDiag.background_count > 0;
    if (!hasBg) {
      issues.push({ text: 'Folder Video nền đang trống → Bấm vào đây để chọn folder Video nền.', view: 'library' });
    }
    const mv = $('opt-meme-video').checked;
    const mi = $('opt-meme-image').checked;
    const ms = $('opt-meme-sound').checked;

    if (mi && !ms) {
      issues.push({ text: 'Khi chọn Ảnh Meme bắt buộc phải bật kèm Tiếng Meme.', view: null });
    }
    if (mv && (mediaDiag.meme_video_count || 0) === 0) {
      issues.push({ text: 'Đang bật Video Meme nhưng folder Video Meme đang trống → Bấm để chọn folder hoặc tắt Video Meme.', view: 'library' });
    }
    if (mi && (mediaDiag.meme_image_count || 0) === 0) {
      issues.push({ text: 'Đang bật Ảnh Meme nhưng folder Ảnh Meme đang trống → Bấm để chọn folder.', view: 'library' });
    }
    if ((mi || ms) && (mediaDiag.meme_sound_count || 0) === 0) {
      issues.push({ text: 'Đang bật Tiếng Meme nhưng folder Tiếng Meme đang trống → Bấm để chọn folder.', view: 'library' });
    }
  }
  return issues;
}

function updateSystemSidebar() {
  $('dot-ffmpeg').className = 'dot ' + (ffmpegReady ? 'ok' : ffmpegReady === false ? 'err' : 'warn');
  $('sys-ffmpeg').textContent = ffmpegReady ? 'FFmpeg sẵn sàng' : ffmpegReady === false ? 'Thiếu FFmpeg' : 'Đang kiểm tra…';

  const vErr = narrationIssue();
  const activeVoices = narrationSettings.voices.filter(Boolean).length || (narrationSettings.voice ? 1 : 0);
  $('dot-eleven').className = 'dot ' + (!vErr ? 'ok' : 'warn');
  $('sys-eleven').textContent = !vErr ? `ElevenLabs · ${activeVoices} giọng` : 'ElevenLabs cần cấu hình';
  $('nav-voice-count').textContent = activeVoices;

  const totalMedia = library.length;
  const memePoolCount = (mediaDiag.meme_video_count || 0) + (mediaDiag.meme_image_count || 0);
  $('dot-media').className = 'dot ' + (mediaDiag.background_count > 0 ? 'ok' : 'warn');
  $('sys-media').textContent = `${mediaDiag.background_count} nền · ${memePoolCount} meme`;
  $('nav-library-count').textContent = totalMedia;
}

function refreshPreflightAndCTA() {
  updateSystemSidebar();
  updateFolderBadgesUI();
  const box = $('preflight-box');
  box.replaceChildren();
  const issues = computePreflightIssues();
  box.classList.toggle('ready', issues.length === 0);

  if (issues.length === 0) {
    const activeVoices = narrationSettings.voices.filter(Boolean).length || (narrationSettings.voice ? 1 : 0);
    const modeNote = $('opt-auto-render').checked
      ? `Sẵn sàng sản xuất · ElevenLabs (${activeVoices} giọng) · ${mediaDiag.background_count} nền`
      : 'Sẵn sàng Crawl hàng loạt (chế độ chỉ lưu dữ liệu, chưa tự render)';
    box.append(node('span', '', modeNote));
  } else {
    for (const iss of issues) {
      if (iss.view) {
        const btn = node('button', 'preflight-issue-btn', iss.text);
        btn.type = 'button';
        btn.addEventListener('click', () => {
          setView(iss.view);
          if (iss.focus) $(iss.focus)?.focus();
        });
        box.append(btn);
      } else {
        box.append(node('span', '', iss.text));
      }
    }
  }

  const parsed = analyzeUrlInput();
  const running = activeRunningBatch();
  const startBtn = $('btn-start-batch');
  if (startBtn.getAttribute('aria-busy') !== 'true') {
    if (running) {
      startBtn.textContent = parsed.urls.length
        ? `+ Thêm ${parsed.urls.length} URL vào hàng đợi đang chạy`
        : 'Đang chạy lô — Dán thêm URL để nối vào hàng đợi';
      startBtn.disabled = parsed.urls.length === 0;
    } else {
      startBtn.textContent = parsed.urls.length
        ? `Bắt đầu sản xuất hàng loạt (${parsed.urls.length} URL)`
        : 'Bắt đầu sản xuất hàng loạt';
      startBtn.disabled = issues.length > 0 || parsed.urls.length === 0;
    }
  }
}

/* LAUNCH OR APPEND BATCH */
$('btn-start-batch').addEventListener('click', () => busy($('btn-start-batch'), async () => {
  const { urls } = analyzeUrlInput();
  if (!urls.length) throw new Error('Dán ít nhất 1 URL TikTok/Threads hợp lệ hoặc nạp file .txt.');

  const running = activeRunningBatch();
  if (running) {
    const res = await postJson(`/api/batch-crawl/${running.id}/append`, { urls });
    $('batch-urls').value = '';
    updateUrlSummary();
    selectedBatchId = running.id;
    await refreshBatches();
    notice(`Đã nối thêm ${res.added} URL vào lô đang chạy (tổng ${res.total} URL).`);
    ensurePolling();
    return;
  }

  const issues = computePreflightIssues();
  if (issues.length) throw new Error(issues[0].text);

  readControlsIntoPreset();
  const created = await postJson('/api/batch-crawl', {
    urls,
    limit: preset.limit,
    auto_render: preset.auto_render,
    options: preset.options,
  });
  $('batch-urls').value = '';
  updateUrlSummary();
  selectedBatchId = created.id;
  currentBatch = created;
  await refreshBatches();
  notice(`Đã khởi chạy lô sản xuất ${created.total} URL.`);
  ensurePolling();
}, 'Đang gửi lô…'));

/* BATCH MONITOR & QUEUE RENDERING */
function formatBatchOptionLabel(b) {
  const dt = b.created ? new Date(b.created * 1000).toLocaleString('vi-VN', {
    hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit',
  }) : '';
  const st = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất', failed: 'Lỗi', cancelled: 'Đã dừng', interrupted: 'Gián đoạn' }[b.status] || b.status;
  return `Lô ${dt} · ${b.completed || 0}/${b.total || 0} URL (${st})`;
}

async function refreshBatches() {
  batches = await (await api('/api/batch-crawl')).json();
  const running = activeRunningBatch();
  $('nav-batch-badge').hidden = !running;

  const sel = $('batch-selector');
  sel.replaceChildren();
  if (!batches.length) {
    sel.append(new Option('Chưa có lô nào', ''));
    currentBatch = null;
    drawBatchMonitor();
    updateGlobalActivity();
    return;
  }
  if (!selectedBatchId || !batches.some(b => b.id === selectedBatchId)) {
    selectedBatchId = (running || batches[0]).id;
  }
  for (const b of batches) {
    sel.append(new Option(formatBatchOptionLabel(b), b.id));
  }
  sel.value = selectedBatchId;
  currentBatch = await (await api('/api/batch-crawl/' + selectedBatchId)).json();
  drawBatchMonitor();
  updateGlobalActivity();
}

$('batch-selector').addEventListener('change', async () => {
  selectedBatchId = $('batch-selector').value;
  if (selectedBatchId) {
    currentBatch = await (await api('/api/batch-crawl/' + selectedBatchId)).json();
    drawBatchMonitor();
  }
});

document.querySelectorAll('[data-batch-filter]').forEach(btn => {
  btn.addEventListener('click', () => {
    batchFilter = btn.dataset.batchFilter;
    document.querySelectorAll('[data-batch-filter]').forEach(el => {
      el.classList.toggle('active', el.dataset.batchFilter === batchFilter);
    });
    drawBatchMonitor();
  });
});

function classifyBatchItem(it) {
  const crawlActive = ['queued', 'crawling'].includes(it.status);
  const renderActive = it.job && ['queued', 'running'].includes(it.job.status);
  if (crawlActive || renderActive) return 'active';
  const crawlFailed = ['failed', 'cancelled', 'interrupted'].includes(it.status);
  const renderFailed = it.job && ['failed', 'cancelled', 'interrupted'].includes(it.job.status);
  if (crawlFailed || renderFailed) return 'failed';
  if (it.status === 'done') return 'done';
  return 'active';
}

function drawBatchMonitor() {
  const list = $('batch-queue-list');
  list.replaceChildren();

  if (!currentBatch) {
    $('kpi-total').textContent = '0';
    $('kpi-crawled').textContent = '0';
    $('kpi-videos').textContent = '0';
    $('kpi-failed').textContent = '0';
    $('flt-count-all').textContent = '0';
    $('flt-count-active').textContent = '0';
    $('flt-count-done').textContent = '0';
    $('flt-count-failed').textContent = '0';
    $('batch-live-strip').hidden = true;
    $('btn-stop-batch').hidden = true;
    $('btn-retry-failed').hidden = true;

    const empty = node('div', 'empty-state');
    empty.append(
      node('h3', '', 'Sẵn sàng nhận hàng loạt URLs'),
      node('p', '', 'Dán danh sách link TikTok / Threads hoặc kéo thả file .txt vào cột bên trái, kiểm tra cấu hình chia video và bấm Bắt đầu sản xuất hàng loạt.')
    );
    list.append(empty);
    return;
  }

  const items = currentBatch.items || [];
  let crawledOk = 0;
  let videoCount = 0;
  let failedCount = 0;
  let activeCount = 0;
  let doneCount = 0;

  for (const it of items) {
    if (it.status === 'done') crawledOk++;
    if (it.job?.files?.length) videoCount += it.job.files.length;
    const bucket = classifyBatchItem(it);
    if (bucket === 'active') activeCount++;
    else if (bucket === 'failed') failedCount++;
    else if (bucket === 'done') doneCount++;
  }

  $('kpi-total').textContent = String(items.length);
  $('kpi-crawled').textContent = `${crawledOk}/${items.length}`;
  $('kpi-videos').textContent = String(videoCount);
  $('kpi-failed').textContent = String(failedCount);

  $('flt-count-all').textContent = String(items.length);
  $('flt-count-active').textContent = String(activeCount);
  $('flt-count-done').textContent = String(doneCount);
  $('flt-count-failed').textContent = String(failedCount);

  const isRunning = ['queued', 'running'].includes(currentBatch.status);
  $('btn-stop-batch').hidden = !isRunning;
  $('btn-retry-failed').hidden = failedCount === 0;
  if (failedCount > 0) {
    $('btn-retry-failed').textContent = `Chạy lại ${failedCount} mục lỗi`;
  }

  $('batch-live-strip').hidden = false;
  const statusMap = {
    queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn tất crawl',
    failed: 'Lỗi lô', cancelled: 'Đã dừng', interrupted: 'Bị gián đoạn',
  };
  const badge = $('batch-status-badge');
  badge.textContent = statusMap[currentBatch.status] || currentBatch.status;
  badge.className = 'badge ' + currentBatch.status;
  $('batch-live-msg').textContent = currentBatch.message || '';

  const bar = $('batch-progress-bar');
  bar.max = Math.max(1, items.length);
  bar.value = currentBatch.completed || 0;

  const filtered = items
    .map((it, idx) => ({ it, idx, bucket: classifyBatchItem(it) }))
    .filter(entry => batchFilter === 'all' || entry.bucket === batchFilter);

  if (!filtered.length) {
    const empty = node('div', 'empty-state');
    empty.append(node('p', '', 'Không có mục nào trong bộ lọc này.'));
    list.append(empty);
    return;
  }

  const crawlLabels = {
    queued: 'Chờ crawl',
    crawling: 'Đang crawl',
    done: 'Crawl xong',
    failed: 'Lỗi crawl',
    cancelled: 'Đã dừng',
    interrupted: 'Gián đoạn',
  };

  for (const { it, idx } of filtered) {
    const row = node('article', 'queue-row' + (it.status === 'crawling' || it.job?.status === 'running' ? ' is-active' : ''));
    const top = node('div', 'queue-row-top');
    const titleWrap = node('div', 'queue-row-title');

    const platform = it.url.includes('tiktok.com') ? 'TikTok' : 'Threads';
    titleWrap.append(
      node('span', 'queue-idx', `#${String(idx + 1).padStart(2, '0')}`),
      node('span', 'platform-tag', platform),
      node('span', 'queue-name', it.name || it.url)
    );

    const badges = node('div', 'queue-badges');
    const cLabel = it.status === 'done'
      ? `${it.comment_count || 0} cmt`
      : crawlLabels[it.status] || it.status;
    badges.append(node('span', 'badge ' + it.status, cLabel));

    if (it.job) {
      const j = it.job;
      const jLabel = j.status === 'done'
        ? `${j.files.length} MP4`
        : j.status === 'running'
          ? `Đang dựng ${j.progress}%`
          : j.status === 'queued'
            ? 'Chờ dựng'
            : j.status === 'cancelled'
              ? 'Hủy dựng'
              : 'Lỗi dựng';
      badges.append(node('span', 'badge ' + j.status, jLabel));
    }

    top.append(titleWrap, badges);
    row.append(top);

    const bottom = node('div', 'queue-row-bottom');
    const msgWrap = node('div');
    msgWrap.append(node('span', '', it.message || ''));
    if (it.name) {
      const urlLink = node('a', 'queue-url', ' · ' + it.url);
      urlLink.href = it.url;
      urlLink.target = '_blank';
      urlLink.rel = 'noopener';
      msgWrap.append(urlLink);
    }
    bottom.append(msgWrap);

    const actions = node('div', 'queue-actions');
    if (it.job?.files?.length) {
      const playBtn = node('button', 'btn btn-primary btn-xs', `▶ Xem (${it.job.files.length})`);
      playBtn.type = 'button';
      playBtn.addEventListener('click', () => openVideoModal(it.name || `URL #${idx + 1}`, it.job, it.project_id));
      actions.append(playBtn);

      const folderBtn = node('button', 'btn btn-secondary btn-xs', 'Thư mục');
      folderBtn.type = 'button';
      folderBtn.addEventListener('click', () => openLocalFolder('project_output', it.project_id));
      actions.append(folderBtn);
    }

    if (it.project_id && (it.comment_count > 0) && !['queued', 'running'].includes(it.job?.status)) {
      const rerenderBtn = node('button', 'btn btn-secondary btn-xs', it.job?.status === 'done' ? 'Render lại' : 'Render ngay');
      rerenderBtn.type = 'button';
      rerenderBtn.addEventListener('click', () => rerenderProject(it.project_id, rerenderBtn));
      actions.append(rerenderBtn);
    }

    if (['failed', 'cancelled', 'interrupted'].includes(it.status)) {
      const retryCrawlBtn = node('button', 'btn btn-warning btn-xs', 'Crawl lại');
      retryCrawlBtn.type = 'button';
      retryCrawlBtn.addEventListener('click', () => retryUrls([it.url], retryCrawlBtn));
      actions.append(retryCrawlBtn);
    }

    if (actions.children.length) bottom.append(actions);
    row.append(bottom);
    list.append(row);
  }
}

$('btn-stop-batch').addEventListener('click', () => busy($('btn-stop-batch'), async () => {
  if (!currentBatch) return;
  await postJson(`/api/batch-crawl/${currentBatch.id}/cancel`, {});
  notice('Đã gửi lệnh dừng lô crawl.');
  await refreshBatches();
}));

async function retryUrls(urls, button) {
  await busy(button, async () => {
    const running = activeRunningBatch();
    if (running) {
      const res = await postJson(`/api/batch-crawl/${running.id}/append`, { urls });
      selectedBatchId = running.id;
      await refreshBatches();
      notice(`Đã đưa ${res.added} URL vào hàng đợi đang chạy.`);
    } else {
      readControlsIntoPreset();
      const created = await postJson('/api/batch-crawl', {
        urls,
        limit: preset.limit,
        auto_render: preset.auto_render,
        options: preset.options,
      });
      selectedBatchId = created.id;
      await refreshBatches();
      notice(`Đã khởi chạy lại ${created.total} URL.`);
    }
    ensurePolling();
  });
}

$('btn-retry-failed').addEventListener('click', () => busy($('btn-retry-failed'), async () => {
  if (!currentBatch) return;
  const crawlRetryUrls = [];
  const renderRetryIds = [];
  for (const it of currentBatch.items || []) {
    if (['failed', 'cancelled', 'interrupted'].includes(it.status)) {
      crawlRetryUrls.push(it.url);
    } else if (it.project_id && it.comment_count > 0 && it.job && ['failed', 'cancelled', 'interrupted'].includes(it.job.status)) {
      renderRetryIds.push(it.project_id);
    }
  }
  if (renderRetryIds.length) {
    readControlsIntoPreset();
    await postJson('/api/projects/render-bulk', {
      project_ids: renderRetryIds,
      use_preset: true,
      options: preset.options,
    });
  }
  if (crawlRetryUrls.length) {
    const running = activeRunningBatch();
    if (running) {
      await postJson(`/api/batch-crawl/${running.id}/append`, { urls: crawlRetryUrls });
      selectedBatchId = running.id;
    } else {
      readControlsIntoPreset();
      const created = await postJson('/api/batch-crawl', {
        urls: crawlRetryUrls,
        limit: preset.limit,
        auto_render: preset.auto_render,
        options: preset.options,
      });
      selectedBatchId = created.id;
    }
  }
  await refreshBatches();
  ensurePolling();
  notice(`Đã xếp hàng chạy lại (${crawlRetryUrls.length} link crawl · ${renderRetryIds.length} bài render).`);
}));

async function rerenderProject(projectId, button) {
  await busy(button, async () => {
    const vErr = narrationIssue();
    if (vErr) throw new Error(vErr);
    readControlsIntoPreset();
    await postJson(`/api/projects/${projectId}/render`, {
      use_preset: true,
      options: preset.options,
    });
    notice('Đã đưa bài viết vào hàng đợi Render MP4.');
    await Promise.all([refreshBatches(), loadCrawlDays()]);
    ensurePolling();
  });
}

/* GLOBAL ACTIVITY & UNIFIED POLLING */
function updateGlobalActivity() {
  const pill = $('global-activity');
  const runningBatch = activeRunningBatch();
  const renderingInBatch = (currentBatch?.items || []).filter(it => it.job && ['queued', 'running'].includes(it.job.status)).length;
  const renderingInHistory = crawlDays.flatMap(d => d.projects).filter(p => p.job && ['queued', 'running'].includes(p.job.status)).length;
  const activeRenders = Math.max(renderingInBatch, renderingInHistory);

  if (runningBatch || activeRenders > 0) {
    pill.classList.add('busy');
    const parts = [];
    if (runningBatch) parts.push(`Crawl ${runningBatch.completed || 0}/${runningBatch.total || 0}`);
    if (activeRenders > 0) parts.push(`Đang dựng ${activeRenders} bài`);
    pill.textContent = parts.join(' · ');
  } else {
    pill.classList.remove('busy');
    pill.textContent = 'Hệ thống sẵn sàng';
  }
  refreshPreflightAndCTA();
}

function shouldKeepPolling() {
  if (activeRunningBatch()) return true;
  if ((currentBatch?.items || []).some(it => it.job && ['queued', 'running'].includes(it.job.status))) return true;
  if (crawlDays.some(d => d.projects.some(p => p.job && ['queued', 'running'].includes(p.job.status)))) return true;
  return false;
}

function ensurePolling() {
  if (pollTimer) return;
  pollTimer = setTimeout(runPollTick, 1800);
}

async function runPollTick() {
  pollTimer = null;
  try {
    await Promise.all([refreshBatches(), loadCrawlDays()]);
  } catch {}
  if (shouldKeepPolling()) {
    pollTimer = setTimeout(runPollTick, 1800);
  }
}

/* VIEW 2: HISTORY & OUTPUTS */
function formatDayLabel(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  if (!y || !m || !d) return dateStr;
  const dt = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((today - dt) / 86400000);
  const prefix = diff === 0 ? 'Hôm nay · ' : diff === 1 ? 'Hôm qua · ' : '';
  return `${prefix}${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`;
}

async function loadCrawlDays() {
  crawlDays = await (await api('/api/crawl-days')).json();
  const totalProjects = crawlDays.reduce((s, d) => s + d.project_count, 0);
  $('nav-history-count').textContent = String(totalProjects);
  if (crawlDays.length && (!selectedDay || !crawlDays.some(d => d.date === selectedDay))) {
    selectedDay = crawlDays[0].date;
  }
  drawHistoryView();
  updateGlobalActivity();
}

function drawHistoryView() {
  const side = $('history-days-list');
  const main = $('history-projects-list');
  side.replaceChildren();
  main.replaceChildren();

  if (!crawlDays.length) {
    $('history-summary-line').textContent = '';
    $('btn-bulk-rerender').hidden = true;
    const empty = node('div', 'empty-state');
    empty.append(
      node('h3', '', 'Kho sản phẩm chưa có dữ liệu'),
      node('p', '', 'Các bài viết sau khi Crawl và Render hàng loạt sẽ tự động gom nhóm theo từng ngày tại đây.')
    );
    main.append(empty);
    return;
  }

  for (const day of crawlDays) {
    const btn = node('button', 'day-card' + (day.date === selectedDay ? ' active' : ''));
    btn.type = 'button';
    const top = node('div', 'day-card-title');
    top.append(node('span', '', formatDayLabel(day.date)), node('span', 'badge', `${day.project_count} bài`));
    const meta = node('div', 'day-card-meta', `${day.comment_count} cmt · ${day.rendered_videos} video MP4`);
    btn.append(top, meta);
    btn.addEventListener('click', () => {
      selectedDay = day.date;
      drawHistoryView();
    });
    side.append(btn);
  }

  const activeDay = crawlDays.find(d => d.date === selectedDay) || crawlDays[0];
  if (!activeDay) return;

  const query = $('history-search').value.trim().toLowerCase();
  const statusFilter = $('history-filter').value;

  const unrenderedIds = activeDay.projects
    .filter(p => p.selected_count > 0 && (!p.job || ['failed', 'cancelled', 'interrupted'].includes(p.job.status)))
    .map(p => p.id);

  const bulkBtn = $('btn-bulk-rerender');
  bulkBtn.hidden = unrenderedIds.length === 0;
  if (unrenderedIds.length > 0) {
    bulkBtn.textContent = `Render ${unrenderedIds.length} bài chưa dựng / lỗi`;
    bulkBtn.onclick = () => busy(bulkBtn, async () => {
      const vErr = narrationIssue();
      if (vErr) throw new Error(vErr);
      readControlsIntoPreset();
      const res = await postJson('/api/projects/render-bulk', {
        project_ids: unrenderedIds,
        use_preset: true,
        options: preset.options,
      });
      notice(`Đã xếp hàng dựng ${res.queued_count} bài viết.`);
      await loadCrawlDays();
      ensurePolling();
    });
  }

  const visible = activeDay.projects.filter(item => {
    if (query) {
      const hay = `${item.name} ${item.author} ${item.url}`.toLowerCase();
      if (!hay.includes(query)) return false;
    }
    if (statusFilter === 'done') return item.job?.status === 'done';
    if (statusFilter === 'running') return item.job && ['queued', 'running'].includes(item.job.status);
    if (statusFilter === 'pending') return !item.job || ['failed', 'cancelled', 'interrupted'].includes(item.job.status);
    return true;
  });

  $('history-summary-line').textContent =
    `Ngày ${formatDayLabel(activeDay.date)} · Hiển thị ${visible.length}/${activeDay.project_count} bài viết · Tổng ${activeDay.rendered_videos} MP4 đã xuất.`;

  if (!visible.length) {
    const empty = node('div', 'empty-state');
    empty.append(node('p', '', 'Không có bài viết nào khớp với bộ lọc hiện tại.'));
    main.append(empty);
    return;
  }

  const statusLabels = {
    queued: 'Chờ dựng', running: 'Đang dựng', done: 'Đã xuất MP4',
    failed: 'Lỗi dựng', cancelled: 'Đã hủy', interrupted: 'Gián đoạn',
  };

  for (const item of visible) {
    const card = node('article', 'history-card' + (item.thumbnail ? '' : ' no-thumb'));
    if (item.thumbnail) {
      const img = node('img', 'history-thumb');
      img.src = `/api/assets/${item.thumbnail}/file`;
      img.alt = item.name;
      img.loading = 'lazy';
      card.append(img);
    }

    const body = node('div', 'history-body');
    const head = node('div', 'history-head');
    head.append(node('h3', '', item.name));

    const statusBadge = node(
      'span',
      'badge ' + (item.job ? item.job.status : ''),
      item.job
        ? (item.job.status === 'done' ? `${item.job.files.length} MP4` : statusLabels[item.job.status] || item.job.status)
        : 'Chưa dựng'
    );
    head.append(statusBadge);
    body.append(head);

    const meta = node('div', 'history-meta');
    const timeStr = item.crawled_at
      ? new Date(item.crawled_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })
      : '';
    if (timeStr) meta.append(node('span', '', `Lúc ${timeStr}`));
    if (item.author) meta.append(node('span', '', `@${item.author.replace(/^@/, '')}`));
    meta.append(node('span', '', `${item.comment_count} bình luận`));
    if (item.project_folder) meta.append(node('code', '', `output/${item.project_folder}`));
    if (item.url) {
      const link = node('a', '', 'Nguồn ↗');
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener';
      meta.append(link);
    }
    body.append(meta);

    if (item.job?.message && item.job.status !== 'done') {
      body.append(node('p', 'hint-line', item.job.message));
    }

    const actions = node('div', 'history-actions');
    if (item.job?.files?.length) {
      const watchBtn = node('button', 'btn btn-primary btn-xs', `▶ Xem MP4 (${item.job.files.length})`);
      watchBtn.type = 'button';
      watchBtn.addEventListener('click', () => openVideoModal(item.name, item.job, item.id));
      actions.append(watchBtn);

      const openDirBtn = node('button', 'btn btn-secondary btn-xs', 'Mở thư mục');
      openDirBtn.type = 'button';
      openDirBtn.addEventListener('click', () => openLocalFolder('project_output', item.id));
      actions.append(openDirBtn);

      for (const file of item.job.files) {
        const dl = node('a', 'btn btn-ghost btn-xs', `⬇ ${file}`);
        dl.href = `/api/jobs/${item.job.id}/files/${encodeURIComponent(file)}`;
        dl.download = file;
        actions.append(dl);
      }
    }

    if (item.job && ['queued', 'running'].includes(item.job.status)) {
      const cancelJobBtn = node('button', 'btn btn-danger btn-xs', 'Hủy dựng');
      cancelJobBtn.type = 'button';
      cancelJobBtn.addEventListener('click', () => busy(cancelJobBtn, async () => {
        await postJson(`/api/jobs/${item.job.id}/cancel`, {});
        await loadCrawlDays();
      }));
      actions.append(cancelJobBtn);
    } else if (item.selected_count > 0) {
      const renderBtn = node('button', 'btn btn-secondary btn-xs', item.job?.status === 'done' ? 'Render lại' : 'Render ngay');
      renderBtn.type = 'button';
      renderBtn.addEventListener('click', () => rerenderProject(item.id, renderBtn));
      actions.append(renderBtn);
    }

    const delBtn = node('button', 'btn btn-ghost btn-xs', 'Xóa');
    delBtn.type = 'button';
    delBtn.addEventListener('click', () => busy(delBtn, async () => {
      await api(`/api/projects/${item.id}`, { method: 'DELETE' });
      await loadCrawlDays();
      notice('Đã xóa mục khỏi lịch sử.');
    }));
    actions.append(delBtn);

    body.append(actions);
    card.append(body);
    main.append(card);
  }
}

$('history-search').addEventListener('input', drawHistoryView);
$('history-filter').addEventListener('change', drawHistoryView);
$('btn-refresh-history').addEventListener('click', () => busy($('btn-refresh-history'), loadCrawlDays));

/* VIDEO PREVIEW MODAL */
function openVideoModal(title, job, projectId) {
  const modal = $('video-modal');
  const player = $('modal-video-player');
  const tabs = $('modal-part-tabs');
  $('modal-video-title').textContent = title;
  tabs.replaceChildren();

  const files = job.files || [];
  if (!files.length) return;

  function selectPart(idx) {
    const file = files[idx];
    const url = `/api/jobs/${job.id}/files/${encodeURIComponent(file)}`;
    player.src = url;
    player.play().catch(() => {});
    const dl = $('modal-download-link');
    dl.href = url;
    dl.download = file;
    Array.from(tabs.children).forEach((b, i) => b.classList.toggle('active', i === idx));
  }

  if (files.length > 1) {
    files.forEach((f, idx) => {
      const btn = node('button', 'chip-btn', `Phần ${idx + 1}`);
      btn.type = 'button';
      btn.addEventListener('click', () => selectPart(idx));
      tabs.append(btn);
    });
  }

  $('modal-open-folder').onclick = () => openLocalFolder('project_output', projectId);
  selectPart(0);
  if (!modal.open) modal.showModal();
}

function closeVideoModal() {
  const modal = $('video-modal');
  const player = $('modal-video-player');
  player.pause();
  player.removeAttribute('src');
  player.load();
  if (modal.open) modal.close();
}

$('btn-close-modal').addEventListener('click', closeVideoModal);
$('video-modal').addEventListener('click', e => {
  if (e.target === $('video-modal')) closeVideoModal();
});

/* VIEW 3: MEDIA LIBRARY & FOLDERS */
function populateBackgroundSelect() {
  const sel = $('opt-background');
  const current = preset.options.background || '';
  sel.replaceChildren();
  sel.append(new Option(`Ngẫu nhiên (${mediaDiag.background_count || 0})`, ''));
  for (const item of library.filter(a => a.kind === 'background')) {
    sel.append(new Option(item.name, item.id));
  }
  if (current && Array.from(sel.options).some(o => o.value === current)) {
    sel.value = current;
  } else {
    sel.value = '';
  }
}

async function loadAssets() {
  const [assetsRes, healthRes] = await Promise.all([
    (await api('/api/assets')).json(),
    (await api('/api/health')).json(),
  ]);
  library = assetsRes;
  ffmpegReady = healthRes.ffmpeg;
  mediaDiag = healthRes.media || mediaDiag;
  populateBackgroundSelect();
  drawLibraryView();
  updateBackgroundVideoPreview();
  refreshPreflightAndCTA();
}

function drawLibraryView() {
  $('count-vid-nen').textContent = String(mediaDiag.background_count || 0);
  $('count-vid-meme').textContent = String(mediaDiag.meme_video_count || 0);
  $('count-img-meme').textContent = String(mediaDiag.meme_image_count || 0);
  $('count-mp3-meme').textContent = String(mediaDiag.meme_sound_count || 0);

  const pairCard = $('meme-pair-card');
  const vidMemes = mediaDiag.meme_video_count || 0;
  const imgMemes = mediaDiag.meme_image_count || 0;
  const sndMemes = mediaDiag.meme_sound_count || 0;
  const exactPairs = mediaDiag.paired_meme_count || 0;
  const randomPairs = mediaDiag.random_paired_count || 0;

  const missingSoundForImages = imgMemes > 0 && sndMemes === 0;
  pairCard.className = 'panel pair-summary-banner ' + (missingSoundForImages ? 'warn' : (vidMemes > 0 || (imgMemes > 0 && sndMemes > 0)) ? 'ok' : '');

  $('pair-status-title').textContent =
    `Kho Meme: ${vidMemes} Video Meme · ${imgMemes} Ảnh Meme (${exactPairs} trùng tên, ${randomPairs} ghép ngẫu nhiên với ${sndMemes} Tiếng Meme)`;
  if (missingSoundForImages) {
    $('pair-status-desc').textContent = 'Đang có Ảnh Meme nhưng folder Tiếng Meme đang trống — hãy chọn folder Tiếng Meme hoặc nạp thêm âm thanh.';
  } else {
    $('pair-status-desc').textContent = 'Ảnh trùng tên với Tiếng (vd 1.png + 1.mp3) được ưu tiên đi cùng nhau; ảnh khác tên sẽ tự ghép ngẫu nhiên với Tiếng Meme.';
  }

  const grid = $('asset-list');
  grid.replaceChildren();
  const shown = library.filter(a => libFilter === 'all' || a.kind === libFilter);

  if (!shown.length) {
    const empty = node('div', 'empty-state');
    empty.append(
      node('h3', '', 'Chưa có tệp nào trong bộ lọc này'),
      node('p', '', 'Bấm "Chọn folder…" trên các thẻ phía trên để trỏ tới thư mục có sẵn trên máy của bạn, hoặc tải tệp lên trực tiếp.')
    );
    grid.append(empty);
    return;
  }

  const kindNames = {
    background: 'Video nền',
    meme_video: 'Video Meme',
    image: 'Ảnh Meme',
    sound: 'Tiếng Meme',
  };
  for (const a of shown) {
    const card = node('article', 'asset-item');
    const isVideo = a.kind === 'background' || a.kind === 'meme_video';
    const media = node(isVideo ? 'video' : a.kind === 'sound' ? 'audio' : 'img');
    media.src = `/api/assets/${a.id}/file`;
    if (a.kind === 'image') {
      media.alt = a.name;
      media.loading = 'lazy';
    } else {
      media.controls = true;
      media.preload = 'metadata';
      if (a.kind === 'background') media.muted = true;
    }
    card.append(media, node('h3', '', a.name));

    const foot = node('div', 'asset-item-foot');
    foot.append(node('p', '', `${kindNames[a.kind] || a.kind} · ${(a.bytes / 1024 / 1024).toFixed(1)} MB`));
    const del = node('button', 'btn btn-ghost btn-xs', 'Xóa');
    del.type = 'button';
    del.addEventListener('click', () => busy(del, async () => {
      await api(`/api/assets/${a.id}`, { method: 'DELETE' });
      await loadAssets();
      notice(`Đã xóa "${a.name}".`);
    }));
    foot.append(del);
    card.append(foot);
    grid.append(card);
  }
}

document.querySelectorAll('[data-lib-filter]').forEach(btn => {
  btn.addEventListener('click', () => {
    libFilter = btn.dataset.libFilter;
    document.querySelectorAll('[data-lib-filter]').forEach(el => {
      el.classList.toggle('active', el.dataset.libFilter === libFilter);
    });
    drawLibraryView();
  });
});

$('btn-upload-assets').addEventListener('click', () => busy($('btn-upload-assets'), async () => {
  const files = Array.from($('asset-files').files || []);
  if (!files.length) throw new Error('Chọn ít nhất một tệp media để tải lên.');
  const kind = $('asset-kind').value;
  for (let i = 0; i < files.length; i++) {
    $('btn-upload-assets').textContent = `Đang nạp ${i + 1}/${files.length}…`;
    const form = new FormData();
    form.append('file', files[i]);
    await api('/api/assets/' + kind, { method: 'POST', body: form });
  }
  $('asset-files').value = '';
  await loadAssets();
  notice(`Đã nạp ${files.length} tệp vào folder.`);
}));

$('btn-refresh-assets').addEventListener('click', () => busy($('btn-refresh-assets'), loadAssets));

/* VIEW 4: ELEVENLABS VOICES */
function voiceFields() {
  return Array.from($('eleven-voice-fields').querySelectorAll('input'), el => el.value.trim());
}

function drawVoiceFields(voices) {
  $('eleven-voice-count').value = voices.length;
  const wrap = $('eleven-voice-fields');
  wrap.replaceChildren();
  voices.forEach((val, idx) => {
    const row = node('div', 'voice-row');
    const id = 'eleven-voice-' + (idx + 1);
    const lbl = node('label', '');
    lbl.htmlFor = id;
    lbl.append(
      document.createTextNode(`Voice ID ${idx + 1}`),
      node('small', '', idx === 0 ? 'Đọc bài gốc + Cmt ngẫu nhiên' : 'Đọc bình luận ngẫu nhiên')
    );

    const inp = node('input');
    inp.type = 'text';
    inp.id = id;
    inp.maxLength = 100;
    inp.autocomplete = 'off';
    inp.pattern = '[A-Za-z0-9_\\-]{0,100}';
    inp.placeholder = 'Nhập Voice ID từ ElevenLabs…';
    inp.value = val;

    const btn = node('button', 'btn btn-secondary btn-xs', `▶ Nghe giọng ${idx + 1}`);
    btn.type = 'button';
    btn.addEventListener('click', () => previewElevenVoice(btn, idx));

    row.append(lbl, inp, btn);
    wrap.append(row);
  });
}

function validateVoiceDraft(requireComplete = true) {
  const countEl = $('eleven-voice-count');
  if (!countEl.checkValidity() || !countEl.value) {
    throw new Error('Số lượng giọng ElevenLabs phải từ 1 đến 120.');
  }
  const voices = voiceFields();
  if (voices.length !== Number(countEl.value) || (voices.length > 1 && (requireComplete || voices.some(Boolean)) && !voices.every(Boolean))) {
    throw new Error(`Hãy nhập đầy đủ cả ${countEl.value} Voice ID ElevenLabs.`);
  }
  if (requireComplete && voices.length === 1 && !voices[0] && !$('elevenlabs_voice').value.trim()) {
    throw new Error('Nhập Voice ID 1 hoặc điền Voice ID mặc định.');
  }
  for (const input of $('eleven-voice-fields').querySelectorAll('input')) {
    if (!input.checkValidity()) {
      throw new Error('Voice ID chỉ được chứa chữ cái, chữ số, dấu gạch ngang (-) hoặc gạch dưới (_).');
    }
  }
  return voices;
}

async function previewElevenVoice(button, index) {
  await busy(button, async () => {
    let voices = validateVoiceDraft(true);
    if (voices.length === 1 && !voices[0]) {
      voices = [$('elevenlabs_voice').value.trim()];
    }
    readControlsIntoPreset();
    const r = await api('/api/voice-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        voice_index: index,
        use_saved_voices: false,
        options: { ...preset.options, provider: 'elevenlabs', elevenlabs_voices: voices },
      }),
    });
    if (voicePreviewUrl) URL.revokeObjectURL(voicePreviewUrl);
    voicePreviewUrl = URL.createObjectURL(await r.blob());
    const player = $('render-voice-player');
    player.src = voicePreviewUrl;
    player.hidden = false;
    player.play().catch(() => {});
  }, 'Đang tạo âm…');
}

$('eleven-voice-count').addEventListener('change', () => {
  const countEl = $('eleven-voice-count');
  if (!countEl.value || !countEl.reportValidity()) return;
  const current = voiceFields();
  drawVoiceFields(Array.from({ length: Number(countEl.value) }, (_, i) => current[i] ?? ''));
  $('voice-settings-status').textContent = 'Có thay đổi chưa lưu — hãy bấm Lưu cấu hình ElevenLabs.';
});

$('settings-form').addEventListener('input', () => {
  $('voice-settings-status').textContent = 'Có thay đổi chưa lưu — hãy bấm Lưu cấu hình ElevenLabs.';
});

async function loadSettings() {
  const cfg = await (await api('/api/settings')).json();
  narrationSettings = {
    key: !!cfg.elevenlabs_key,
    voice: cfg.elevenlabs_voice || '',
    voices: cfg.elevenlabs_voices || (cfg.elevenlabs_voice ? [''] : ['', '', '']),
    model: cfg.elevenlabs_model || 'eleven_v3',
  };
  $('elevenlabs_voice').value = narrationSettings.voice;
  $('elevenlabs_model').value = narrationSettings.model;
  drawVoiceFields(narrationSettings.voices);

  const keyBadge = $('eleven-status');
  keyBadge.textContent = cfg.elevenlabs_key ? 'Đã lưu API Key' : 'Chưa lưu Key';
  keyBadge.className = 'badge ' + (cfg.elevenlabs_key ? 'done' : 'failed');
  $('voice-settings-status').textContent = 'Đang dùng cấu hình đã lưu trên máy.';
  refreshPreflightAndCTA();
}

$('settings-form').addEventListener('submit', e => {
  e.preventDefault();
  busy($('btn-save-voices'), async () => {
    const voices = validateVoiceDraft(false);
    const payload = {
      elevenlabs_voices: voices,
      elevenlabs_key: $('elevenlabs_key').value,
      elevenlabs_voice: $('elevenlabs_voice').value,
      elevenlabs_model: $('elevenlabs_model').value || 'eleven_v3',
    };
    await postJson('/api/settings', payload);
    $('elevenlabs_key').value = '';
    await loadSettings();
    notice('Đã lưu cấu hình ElevenLabs thành công.');
  }, 'Đang lưu…');
});

/* INITIALIZATION */
async function init() {
  try {
    const [healthRes, savedPreset] = await Promise.all([
      (await api('/api/health')).json(),
      (await api('/api/preset')).json(),
    ]);
    ffmpegReady = healthRes.ffmpeg;
    mediaDiag = healthRes.media || mediaDiag;
    preset = { ...defaultPreset(), ...savedPreset, options: { ...defaultPreset().options, ...(savedPreset.options || {}) } };

    await Promise.all([loadSettings(), loadAssets(), loadCrawlDays()]);
    applyPresetToControls();
    updateUrlSummary();
    await refreshBatches();
    if (shouldKeepPolling()) ensurePolling();
    if (!ffmpegReady) {
      notice('Chưa tìm thấy FFmpeg trên PATH. Hãy cài FFmpeg trước khi Render MP4.', true);
    }
  } catch (err) {
    notice('Không kết nối được Engine cục bộ: ' + err.message, true);
  }
}

init();
