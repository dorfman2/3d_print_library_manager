/**
 * 3D Print Library — Frontend Application
 *
 * Single-page app with hash-based routing, folder/file grid,
 * sidebar filtering, Three.js thumbnail rendering, and scan management.
 */

/* global THREE */

// ---------------------------------------------------------------------------
// Logger (browser wrapper per js-logging-standards)
// ---------------------------------------------------------------------------

const logger = {
  error: (msg, data) => console.error(msg, data),
  warn: (msg, data) => console.warn(msg, data),
  info: (msg, data) => console.info(msg, data),
  debug: (msg, data) => console.debug(msg, data)
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
  view: 'level1',          // 'level1' or 'level2'
  folderId: null,          // Current folder ID in Level 2
  folderData: null,        // Current folder detail data
  folders: [],             // Cached folder list
  categories: [],          // Cached categories
  tags: [],                // Cached tags
  filters: {
    category: null,
    tag: null,
    search: '',
    format: null
  }
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
  try {
    const resp = await fetch(path, options);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      logger.error('API error', { path, status: resp.status, error: err });
      return null;
    }
    return resp.json();
  } catch (e) {
    logger.error('API fetch failed', { path, error: e.message });
    return null;
  }
}

async function fetchCategories() {
  const data = await api('/api/categories');
  if (data) state.categories = data;
  return data;
}

async function fetchTags() {
  const data = await api('/api/tags');
  if (data) state.tags = data;
  return data;
}

async function fetchFolders() {
  const params = new URLSearchParams();
  if (state.filters.category) params.set('category', state.filters.category);
  if (state.filters.tag) params.set('tag', state.filters.tag);
  if (state.filters.format) params.set('format', state.filters.format);

  const url = '/api/folders' + (params.toString() ? '?' + params : '');
  const data = await api(url);
  if (data) state.folders = data;
  return data;
}

async function fetchFolderDetail(id) {
  return api(`/api/folders/${id}`);
}

// ---------------------------------------------------------------------------
// Routing
// ---------------------------------------------------------------------------

function navigate(hash) {
  window.location.hash = hash;
}

function parseRoute() {
  const hash = window.location.hash || '#/';
  const match = hash.match(/^#\/folder\/(\d+)$/);
  if (match) {
    return { view: 'level2', folderId: parseInt(match[1], 10) };
  }
  return { view: 'level1', folderId: null };
}

async function handleRoute() {
  const route = parseRoute();
  state.view = route.view;
  state.folderId = route.folderId;

  if (state.view === 'level2') {
    await renderLevel2();
  } else {
    await renderLevel1();
  }
}

// ---------------------------------------------------------------------------
// Sidebar rendering
// ---------------------------------------------------------------------------

function renderCategories() {
  const list = document.getElementById('category-list');
  list.innerHTML = '';

  // "All" option
  const allLi = document.createElement('li');
  allLi.className = 'sidebar__item' + (!state.filters.category ? ' sidebar__item--active' : '');
  allLi.textContent = 'All';
  allLi.addEventListener('click', () => {
    state.filters.category = null;
    refreshLevel1();
  });
  list.appendChild(allLi);

  for (const cat of state.categories) {
    const li = document.createElement('li');
    li.className = 'sidebar__item' + (state.filters.category === cat.name ? ' sidebar__item--active' : '');
    const nameSpan = document.createElement('span');
    nameSpan.textContent = cat.name.replace(/^\d+\s*-\s*/, '');
    const countSpan = document.createElement('span');
    countSpan.className = 'sidebar__count';
    countSpan.textContent = cat.count;
    li.appendChild(nameSpan);
    li.appendChild(countSpan);
    li.addEventListener('click', () => {
      state.filters.category = cat.name;
      refreshLevel1();
    });
    list.appendChild(li);
  }
}

function renderTags() {
  const list = document.getElementById('tag-list');
  list.innerHTML = '';

  for (const tag of state.tags) {
    const li = document.createElement('li');
    li.className = 'sidebar__item' + (state.filters.tag === tag.name ? ' sidebar__item--active' : '');
    const nameSpan = document.createElement('span');
    nameSpan.textContent = tag.name;
    const countSpan = document.createElement('span');
    countSpan.className = 'sidebar__count';
    countSpan.textContent = tag.count;
    li.appendChild(nameSpan);
    li.appendChild(countSpan);
    li.addEventListener('click', () => {
      state.filters.tag = state.filters.tag === tag.name ? null : tag.name;
      refreshLevel1();
    });
    list.appendChild(li);
  }
}

// ---------------------------------------------------------------------------
// Filter chips
// ---------------------------------------------------------------------------

function renderFilterChips() {
  const container = document.getElementById('filter-chips');
  container.innerHTML = '';

  if (state.filters.category) {
    container.appendChild(createChip(
      'Category: ' + state.filters.category.replace(/^\d+\s*-\s*/, ''),
      () => { state.filters.category = null; refreshLevel1(); }
    ));
  }
  if (state.filters.tag) {
    container.appendChild(createChip(
      'Tag: ' + state.filters.tag,
      () => { state.filters.tag = null; refreshLevel1(); }
    ));
  }
  if (state.filters.search) {
    container.appendChild(createChip(
      'Search: ' + state.filters.search,
      () => {
        state.filters.search = '';
        document.getElementById('search-input').value = '';
        refreshLevel1();
      }
    ));
  }
}

function createChip(label, onRemove) {
  const chip = document.createElement('div');
  chip.className = 'chip';
  chip.setAttribute('role', 'listitem');
  const text = document.createElement('span');
  text.textContent = label;
  const btn = document.createElement('button');
  btn.className = 'chip__remove';
  btn.textContent = '×';
  btn.setAttribute('aria-label', 'Remove filter: ' + label);
  btn.addEventListener('click', onRemove);
  chip.appendChild(text);
  chip.appendChild(btn);
  return chip;
}

// ---------------------------------------------------------------------------
// Level 1: Folder Grid
// ---------------------------------------------------------------------------

async function renderLevel1() {
  document.getElementById('breadcrumb').hidden = true;
  await fetchFolders();
  renderCategories();
  renderTags();
  renderFilterChips();
  renderFolderGrid();
}

async function refreshLevel1() {
  await fetchFolders();
  renderCategories();
  renderTags();
  renderFilterChips();
  renderFolderGrid();
}

function renderFolderGrid() {
  const grid = document.getElementById('card-grid');
  grid.innerHTML = '';

  let folders = state.folders;

  // Client-side search filter
  if (state.filters.search) {
    const q = state.filters.search.toLowerCase();
    folders = folders.filter(f =>
      f.name.toLowerCase().includes(q) ||
      (f.tags && f.tags.some(t => t.toLowerCase().includes(q)))
    );
  }

  if (folders.length === 0) {
    grid.innerHTML = '<p style="color:var(--text-muted);grid-column:1/-1;">No folders match the current filters.</p>';
    return;
  }

  for (const folder of folders) {
    const card = document.createElement('div');
    card.className = 'card';
    card.setAttribute('role', 'listitem');
    card.addEventListener('click', () => navigate(`#/folder/${folder.id}`));

    // Thumbnail
    const thumb = document.createElement('div');
    thumb.className = 'card__thumb';
    if (folder.cover_thumbnail && folder.cover_thumbnail !== '__failed__') {
      const img = document.createElement('img');
      img.src = `/thumbnails/${folder.cover_thumbnail}`;
      img.alt = folder.name;
      img.loading = 'lazy';
      thumb.appendChild(img);
    } else {
      const icon = document.createElement('img');
      icon.className = 'card__icon';
      icon.src = '/static/icons/folder.svg';
      icon.alt = '';
      thumb.appendChild(icon);
    }
    card.appendChild(thumb);

    // Body
    const body = document.createElement('div');
    body.className = 'card__body';

    const name = document.createElement('div');
    name.className = 'card__name';
    name.textContent = folder.name;
    name.title = folder.name;
    body.appendChild(name);

    const meta = document.createElement('div');
    meta.className = 'card__meta';
    const count = document.createElement('span');
    count.className = 'card__count';
    count.textContent = folder.file_count + ' files';
    meta.appendChild(count);

    // Format badges
    if (folder.formats) {
      for (const fmt of folder.formats.slice(0, 3)) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = fmt;
        meta.appendChild(badge);
      }
    }
    body.appendChild(meta);

    // Tag chips
    if (folder.tags && folder.tags.length > 0) {
      const tagsDiv = document.createElement('div');
      tagsDiv.className = 'card__tags';
      for (const t of folder.tags.slice(0, 3)) {
        const tagSpan = document.createElement('span');
        tagSpan.className = 'card__tag';
        tagSpan.textContent = t;
        tagsDiv.appendChild(tagSpan);
      }
      body.appendChild(tagsDiv);
    }

    card.appendChild(body);
    grid.appendChild(card);
  }
}

// ---------------------------------------------------------------------------
// Level 2: File Grid with Folder Detail
// ---------------------------------------------------------------------------

async function renderLevel2() {
  const detail = await fetchFolderDetail(state.folderId);
  if (!detail) {
    navigate('#/');
    return;
  }
  state.folderData = detail;

  // Show breadcrumb
  const breadcrumb = document.getElementById('breadcrumb');
  breadcrumb.hidden = false;
  document.getElementById('breadcrumb-text').textContent = detail.name;

  // Render format filter in sidebar for Level 2
  renderLevel2FormatFilter(detail);

  // Render folder detail header (tags + notes)
  const grid = document.getElementById('card-grid');
  grid.innerHTML = '';

  // Folder detail section
  const detailSection = document.createElement('div');
  detailSection.className = 'folder-detail';
  detailSection.style.gridColumn = '1 / -1';

  // Tags
  const tagsDiv = document.createElement('div');
  tagsDiv.className = 'folder-detail__tags';
  renderFolderTags(tagsDiv, detail);
  detailSection.appendChild(tagsDiv);

  // Notes
  const notes = document.createElement('textarea');
  notes.className = 'folder-detail__notes';
  notes.placeholder = 'Add notes…';
  notes.value = detail.notes || '';
  notes.addEventListener('blur', async () => {
    await api(`/api/folders/${detail.id}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notes.value })
    });
  });
  detailSection.appendChild(notes);
  grid.appendChild(detailSection);

  // If container, show child folders
  if (!detail.is_leaf && detail.children && detail.children.length > 0) {
    for (const child of detail.children) {
      grid.appendChild(createFolderCard(child));
    }
  }

  // Show files
  if (detail.files && detail.files.length > 0) {
    let files = detail.files;
    // Level 2 format filter
    if (state.filters.format) {
      files = files.filter(f => f.format === state.filters.format);
    }
    for (const file of files) {
      grid.appendChild(createFileCard(file, detail));
    }
  }

  // Trigger thumbnail rendering for files without thumbnails
  if (typeof renderThumbnails === 'function') {
    renderThumbnails();
  }
}

function renderLevel2FormatFilter(detail) {
  const tagList = document.getElementById('tag-list');
  tagList.innerHTML = '';

  if (!detail.files || detail.files.length === 0) return;

  // Get unique formats in this folder
  const formats = [...new Set(detail.files.map(f => f.format))].sort();
  if (formats.length <= 1) return;

  // "All formats" option
  const allLi = document.createElement('li');
  allLi.className = 'sidebar__item' + (!state.filters.format ? ' sidebar__item--active' : '');
  allLi.textContent = 'All formats';
  allLi.addEventListener('click', () => {
    state.filters.format = null;
    renderLevel2();
  });
  tagList.appendChild(allLi);

  for (const fmt of formats) {
    const count = detail.files.filter(f => f.format === fmt).length;
    const li = document.createElement('li');
    li.className = 'sidebar__item' + (state.filters.format === fmt ? ' sidebar__item--active' : '');
    const nameSpan = document.createElement('span');
    nameSpan.textContent = fmt.toUpperCase();
    const countSpan = document.createElement('span');
    countSpan.className = 'sidebar__count';
    countSpan.textContent = count;
    li.appendChild(nameSpan);
    li.appendChild(countSpan);
    li.addEventListener('click', () => {
      state.filters.format = state.filters.format === fmt ? null : fmt;
      renderLevel2();
    });
    tagList.appendChild(li);
  }
}

function renderFolderTags(container, detail) {
  container.innerHTML = '';
  const tags = detail.tags || [];
  for (const tag of tags) {
    const tagEl = document.createElement('span');
    tagEl.className = 'folder-detail__tag';
    tagEl.textContent = tag;
    const removeBtn = document.createElement('button');
    removeBtn.textContent = '×';
    removeBtn.setAttribute('aria-label', 'Remove tag ' + tag);
    removeBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      await api(`/api/folders/${detail.id}/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' });
      detail.tags = detail.tags.filter(t => t !== tag);
      renderFolderTags(container, detail);
    });
    tagEl.appendChild(removeBtn);
    container.appendChild(tagEl);
  }

  // Add tag button
  const addBtn = document.createElement('button');
  addBtn.className = 'folder-detail__add-tag';
  addBtn.textContent = '+ Tag';
  addBtn.addEventListener('click', async () => {
    const name = prompt('Tag name:');
    if (name && name.trim()) {
      await api(`/api/folders/${detail.id}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim() })
      });
      detail.tags.push(name.trim());
      renderFolderTags(container, detail);
      // Refresh sidebar tags
      await fetchTags();
      renderTags();
    }
  });
  container.appendChild(addBtn);
}

function createFolderCard(folder) {
  const card = document.createElement('div');
  card.className = 'card';
  card.setAttribute('role', 'listitem');
  card.addEventListener('click', () => navigate(`#/folder/${folder.id}`));

  const thumb = document.createElement('div');
  thumb.className = 'card__thumb';
  const icon = document.createElement('img');
  icon.className = 'card__icon';
  icon.src = '/static/icons/folder.svg';
  icon.alt = '';
  thumb.appendChild(icon);
  card.appendChild(thumb);

  const body = document.createElement('div');
  body.className = 'card__body';
  const name = document.createElement('div');
  name.className = 'card__name';
  name.textContent = folder.name || folder.raw_name;
  name.title = folder.name || folder.raw_name;
  body.appendChild(name);
  card.appendChild(body);
  return card;
}

function createFileCard(file, folder) {
  const card = document.createElement('div');
  card.className = 'card';
  card.setAttribute('role', 'listitem');
  card.dataset.fileId = file.id;
  card.dataset.format = file.format;
  card.dataset.hash = file.content_hash || '';

  // Thumbnail
  const thumb = document.createElement('div');
  thumb.className = 'card__thumb';

  if (file.thumbnail && file.thumbnail !== '__failed__') {
    const img = document.createElement('img');
    img.src = `/thumbnails/${file.thumbnail}`;
    img.alt = file.filename;
    img.loading = 'lazy';
    thumb.appendChild(img);
  } else if (!file.thumbnail && RENDERABLE_FORMATS.has(file.format)) {
    // No thumbnail yet and renderable — show placeholder, will render later
    const icon = document.createElement('img');
    icon.className = 'card__icon card__icon--pending';
    icon.src = getFormatIcon(file.format);
    icon.alt = file.format;
    thumb.appendChild(icon);
  } else {
    const icon = document.createElement('img');
    icon.className = 'card__icon';
    icon.src = getFormatIcon(file.format);
    icon.alt = file.format;
    thumb.appendChild(icon);
  }
  card.appendChild(thumb);

  // Body
  const body = document.createElement('div');
  body.className = 'card__body';

  const name = document.createElement('div');
  name.className = 'card__name';
  name.textContent = file.filename;
  name.title = file.filename;
  body.appendChild(name);

  const meta = document.createElement('div');
  meta.className = 'card__meta';
  const badge = document.createElement('span');
  badge.className = 'badge';
  badge.textContent = file.format;
  meta.appendChild(badge);
  const size = document.createElement('span');
  size.className = 'card__count';
  size.textContent = formatSize(file.size_bytes);
  meta.appendChild(size);
  body.appendChild(meta);
  card.appendChild(body);

  // Actions
  const actions = document.createElement('div');
  actions.className = 'card__actions';

  const openBtn = document.createElement('button');
  openBtn.textContent = 'Open';
  openBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    api(`/api/open/${file.id}`, { method: 'POST' });
  });
  actions.appendChild(openBtn);

  const revealBtn = document.createElement('button');
  revealBtn.textContent = 'Reveal';
  revealBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    api(`/api/reveal/${file.id}`, { method: 'POST' });
  });
  actions.appendChild(revealBtn);

  const coverBtn = document.createElement('button');
  coverBtn.textContent = 'Cover';
  coverBtn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await api(`/api/folders/${folder.id}/cover`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: file.id })
    });
    coverBtn.textContent = '✓ Cover';
  });
  actions.appendChild(coverBtn);

  card.appendChild(actions);
  return card;
}

// ---------------------------------------------------------------------------
// Utility
// ---------------------------------------------------------------------------

function getFormatIcon(format) {
  const iconMap = {
    step: '/static/icons/step.svg',
    stp: '/static/icons/step.svg',
    f3d: '/static/icons/f3d.svg',
    bgcode: '/static/icons/bgcode.svg',
    pdf: '/static/icons/pdf.svg'
  };
  return iconMap[format] || '/static/icons/folder.svg';
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return size.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function setupSearch() {
  const input = document.getElementById('search-input');
  let debounceTimer = null;
  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.filters.search = input.value.trim();
      if (state.view === 'level1') {
        renderFilterChips();
        renderFolderGrid();
      }
    }, 200);
  });
}

// ---------------------------------------------------------------------------
// Back button
// ---------------------------------------------------------------------------

function setupBackButton() {
  document.getElementById('back-btn').addEventListener('click', () => {
    navigate('#/');
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  setupSearch();
  setupBackButton();
  await Promise.all([fetchCategories(), fetchTags()]);
  await handleRoute();
  window.addEventListener('hashchange', handleRoute);
}

document.addEventListener('DOMContentLoaded', init);

// ---------------------------------------------------------------------------
// Three.js Thumbnail Renderer
// ---------------------------------------------------------------------------

const RENDERABLE_FORMATS = new Set(['stl', '3mf', 'obj']);
const MAX_CONCURRENT_RENDERS = 3;
let activeRenders = 0;
const renderQueue = [];
let webglAvailable = null;

function checkWebGL() {
  if (webglAvailable !== null) return webglAvailable;
  try {
    const canvas = document.createElement('canvas');
    webglAvailable = !!(
      canvas.getContext('webgl') || canvas.getContext('experimental-webgl')
    );
  } catch (e) {
    webglAvailable = false;
  }
  if (!webglAvailable) {
    document.getElementById('webgl-banner').hidden = false;
  }
  return webglAvailable;
}

function renderThumbnails() {
  if (!checkWebGL()) return;

  const cards = document.querySelectorAll('.card[data-file-id]');
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const card = entry.target;
        observer.unobserve(card);
        enqueueRender(card);
      }
    }
  }, { rootMargin: '200px' });

  for (const card of cards) {
    const fileId = card.dataset.fileId;
    const format = card.dataset.format;
    const thumb = card.querySelector('.card__thumb img');

    // Only render if: renderable format, no existing thumbnail, not failed
    if (!RENDERABLE_FORMATS.has(format)) continue;
    if (thumb && !thumb.classList.contains('card__icon')) continue;
    // Skip if thumbnail is already cached (check data attribute)
    if (card.dataset.thumbnailStatus === 'done' || card.dataset.thumbnailStatus === 'failed') continue;

    observer.observe(card);
  }
}

function enqueueRender(card) {
  renderQueue.push(card);
  processRenderQueue();
}

function processRenderQueue() {
  while (activeRenders < MAX_CONCURRENT_RENDERS && renderQueue.length > 0) {
    const card = renderQueue.shift();
    activeRenders++;
    renderSingleThumbnail(card).finally(() => {
      activeRenders--;
      processRenderQueue();
    });
  }
}

// Shared renderer — prevents WebGL context exhaustion
let _sharedRenderer = null;

function getSharedRenderer() {
  if (!_sharedRenderer) {
    _sharedRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    _sharedRenderer.setSize(256, 256);
  }
  // Check for context loss and recreate if needed
  if (_sharedRenderer.getContext().isContextLost()) {
    logger.warn('WebGL context lost, recreating renderer');
    _sharedRenderer.dispose();
    _sharedRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    _sharedRenderer.setSize(256, 256);
  }
  return _sharedRenderer;
}

function disposeObject(obj) {
  if (!obj) return;
  if (obj.geometry) {
    obj.geometry.dispose();
  }
  if (obj.material) {
    if (Array.isArray(obj.material)) {
      obj.material.forEach(m => m.dispose());
    } else {
      obj.material.dispose();
    }
  }
  if (obj.children) {
    obj.children.forEach(child => disposeObject(child));
  }
}

async function renderSingleThumbnail(card) {
  const fileId = parseInt(card.dataset.fileId, 10);
  const format = card.dataset.format;

  try {
    // Fetch raw file
    const resp = await fetch(`/api/files/${fileId}/raw`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const buffer = await resp.arrayBuffer();

    // Load geometry
    let object;
    if (format === 'stl') {
      const loader = new THREE.STLLoader();
      const geometry = loader.parse(buffer);
      const material = new THREE.MeshPhongMaterial({
        color: 0x808080,
        specular: 0x111111,
        shininess: 50
      });
      object = new THREE.Mesh(geometry, material);
    } else if (format === 'obj') {
      const loader = new THREE.OBJLoader();
      const text = new TextDecoder().decode(buffer);
      object = loader.parse(text);
    } else if (format === '3mf') {
      const loader = new THREE.ThreeMFLoader();
      object = loader.parse(buffer);
    }

    if (!object) throw new Error('No geometry loaded');

    // Setup scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xe8e8e8);

    // Lighting
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dir1 = new THREE.DirectionalLight(0xffffff, 0.8);
    dir1.position.set(1, 2, 3);
    scene.add(dir1);
    const dir2 = new THREE.DirectionalLight(0xffffff, 0.4);
    dir2.position.set(-1, -1, -2);
    scene.add(dir2);

    scene.add(object);

    // Auto-frame camera
    const box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    if (maxDim === 0 || !isFinite(maxDim)) throw new Error('Empty or invalid geometry');

    const distance = maxDim * 1.8;
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, distance * 10);
    camera.position.set(
      center.x + distance * 0.5,
      center.y + distance * 0.5,
      center.z + distance
    );
    camera.lookAt(center);

    // Render using shared renderer
    const renderer = getSharedRenderer();
    renderer.render(scene, camera);

    // Get image data
    const dataUrl = renderer.domElement.toDataURL('image/png');

    // Cleanup scene objects (but NOT the renderer)
    disposeObject(object);
    scene.clear();

    // POST to server
    const uploadResp = await api('/api/thumbnails', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, image: dataUrl })
    });

    if (uploadResp && uploadResp.thumbnail) {
      const thumbDiv = card.querySelector('.card__thumb');
      thumbDiv.innerHTML = '';
      const img = document.createElement('img');
      img.src = `/thumbnails/${uploadResp.thumbnail}`;
      img.alt = '';
      thumbDiv.appendChild(img);
    }
    card.dataset.thumbnailStatus = 'done';
  } catch (e) {
    logger.warn('Thumbnail render failed', { fileId, format, error: e.message });
    card.dataset.thumbnailStatus = 'failed';
    // Mark as failed so we don't retry
    api('/api/thumbnails', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, image: '__failed__' })
    }).catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function setupSearch() {
  const input = document.getElementById('search-input');
  let debounceTimer = null;
  input.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.filters.search = input.value.trim();
      if (state.view === 'level1') {
        renderFilterChips();
        renderFolderGrid();
      }
    }, 200);
  });
}

// ---------------------------------------------------------------------------
// Back button
// ---------------------------------------------------------------------------

function setupBackButton() {
  document.getElementById('back-btn').addEventListener('click', () => {
    navigate('#/');
  });
}

// ---------------------------------------------------------------------------
// Scan Progress
// ---------------------------------------------------------------------------

let scanPollTimer = null;

function setupScanButton() {
  const btn = document.getElementById('scan-btn');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    const result = await api('/api/scan', { method: 'POST' });
    if (result && result.status === 'started') {
      showScanProgress();
      startScanPolling();
    } else {
      btn.disabled = false;
    }
  });
}

function showScanProgress() {
  document.getElementById('scan-progress').hidden = false;
}

function hideScanProgress() {
  document.getElementById('scan-progress').hidden = true;
  document.getElementById('scan-btn').disabled = false;
}

function startScanPolling() {
  scanPollTimer = setInterval(async () => {
    const status = await api('/api/scan/status');
    if (!status) return;

    const fill = document.getElementById('progress-fill');
    const text = document.getElementById('progress-text');

    if (status.status === 'running') {
      const pct = status.total > 0
        ? Math.round((status.processed / status.total) * 100)
        : 0;
      fill.style.width = pct + '%';
      text.textContent = `Scanning... ${status.processed || 0}/${status.total || '?'}`;
    } else if (status.status === 'complete' || status.status === 'error') {
      clearInterval(scanPollTimer);
      scanPollTimer = null;
      hideScanProgress();
      // Refresh data
      await Promise.all([fetchCategories(), fetchTags()]);
      await handleRoute();
    }
  }, 2000);
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  checkWebGL();
  setupSearch();
  setupBackButton();
  setupScanButton();
  await Promise.all([fetchCategories(), fetchTags()]);
  await handleRoute();
  window.addEventListener('hashchange', handleRoute);
}

document.addEventListener('DOMContentLoaded', init);
