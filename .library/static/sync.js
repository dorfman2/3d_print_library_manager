/**
 * Sync Panel JavaScript
 *
 * Handles configuration loading/saving, sync preview, sync execution,
 * and schedule management for the 3D Print Library sync panel.
 */

const logger = {
    error: (msg, data) => console.error(msg, data),
    warn: (msg, data) => console.warn(msg, data),
    info: (msg, data) => console.info(msg, data),
    debug: (msg, data) => console.debug(msg, data)
};

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────

let pollInterval = null;

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────

async function init() {
    await loadConfig();
    await loadStatus();
    startPolling();
}

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────

async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const cfg = await resp.json();

        document.getElementById('sync-source').value = cfg.source_folder || '';
        document.getElementById('sync-library').value = cfg.library_folder || '';
        document.getElementById('sync-interval').value = cfg.sync_interval_minutes || 60;

        // Set schedule radio
        const radios = document.querySelectorAll('input[name="schedule"]');
        radios.forEach(r => {
            r.checked = (r.value === 'on' && cfg.sync_enabled) ||
                        (r.value === 'off' && !cfg.sync_enabled);
        });
    } catch (err) {
        logger.error('Failed to load config', { error: err.message });
    }
}

async function saveConfig() {
    const source = document.getElementById('sync-source').value;
    const library = document.getElementById('sync-library').value;
    const interval = parseInt(document.getElementById('sync-interval').value, 10) || 60;
    const enabled = document.querySelector('input[name="schedule"]:checked').value === 'on';

    try {
        // Save folder config
        const configResp = await fetch('/api/config', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_folder: source,
                library_folder: library,
                sync_interval_minutes: interval,
                sync_enabled: enabled,
            }),
        });

        if (!configResp.ok) {
            const err = await configResp.json();
            appendLog('error', err.error || 'Config save failed');
            return;
        }

        // Update scheduler
        const schedResp = await fetch('/api/sync/schedule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled, interval_minutes: interval }),
        });

        if (schedResp.ok) {
            appendLog('info', 'Settings saved successfully.');
        }

        await loadStatus();
    } catch (err) {
        logger.error('Failed to save config', { error: err.message });
        appendLog('error', 'Failed to save: ' + err.message);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Status
// ─────────────────────────────────────────────────────────────────────────────

async function loadStatus() {
    try {
        const resp = await fetch('/api/sync/status');
        const status = await resp.json();

        const stateEl = document.getElementById('sync-state');
        stateEl.textContent = status.state.charAt(0).toUpperCase() + status.state.slice(1);
        stateEl.className = 'status-value status-' + status.state;

        document.getElementById('sync-last-run').textContent =
            status.last_run ? formatTime(status.last_run) : 'Never';
        document.getElementById('sync-next-run').textContent =
            status.next_run ? formatTime(status.next_run) : '—';
    } catch (err) {
        logger.debug('Status poll failed', { error: err.message });
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(loadStatus, 5000);
}

function formatTime(iso) {
    try {
        const d = new Date(iso);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return iso;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sync Operations
// ─────────────────────────────────────────────────────────────────────────────

async function runPreview() {
    const btn = document.getElementById('btn-preview');
    btn.disabled = true;
    btn.textContent = 'Running…';
    clearLog();
    appendLog('info', 'Running preview (dry run)…');

    try {
        const resp = await fetch('/api/sync/preview', { method: 'POST' });

        if (resp.status === 409) {
            appendLog('warn', 'Sync is already running. Please wait.');
            return;
        }

        const result = await resp.json();
        renderResult(result, true);
    } catch (err) {
        logger.error('Preview failed', { error: err.message });
        appendLog('error', 'Preview failed: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Preview (Dry Run)';
    }
}

async function runSync() {
    const btn = document.getElementById('btn-sync');
    btn.disabled = true;
    btn.textContent = 'Syncing…';
    clearLog();
    appendLog('info', 'Starting sync…');

    try {
        const resp = await fetch('/api/sync/run', { method: 'POST' });

        if (resp.status === 409) {
            appendLog('warn', 'Sync is already running. Please wait.');
            btn.disabled = false;
            btn.textContent = 'Run Sync Now';
            return;
        }

        appendLog('info', 'Sync started in background. Polling for completion…');

        // Poll until complete
        let attempts = 0;
        const maxAttempts = 120;
        const pollDelay = 2000;

        const pollDone = setInterval(async () => {
            attempts++;
            const statusResp = await fetch('/api/sync/status');
            const status = await statusResp.json();

            if (status.state !== 'running' || attempts >= maxAttempts) {
                clearInterval(pollDone);
                btn.disabled = false;
                btn.textContent = 'Run Sync Now';
                appendLog('info', 'Sync complete. Check library for new items.');
                await loadStatus();
            }
        }, pollDelay);

    } catch (err) {
        logger.error('Sync failed', { error: err.message });
        appendLog('error', 'Sync failed: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Run Sync Now';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Log Rendering
// ─────────────────────────────────────────────────────────────────────────────

function clearLog() {
    document.getElementById('sync-log').innerHTML = '';
}

function appendLog(level, message) {
    const log = document.getElementById('sync-log');
    // Remove placeholder if present
    const placeholder = log.querySelector('.log-placeholder');
    if (placeholder) placeholder.remove();

    const entry = document.createElement('div');
    entry.className = 'log-entry log-' + level;
    entry.textContent = message;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function renderResult(result, isDryRun) {
    const prefix = isDryRun ? '[PREVIEW] ' : '';

    if (result.zips_extracted && result.zips_extracted.length > 0) {
        for (const zip of result.zips_extracted) {
            appendLog('zip', prefix + 'ZIP extracted: ' + zip);
        }
    }

    if (result.zips_deleted && result.zips_deleted.length > 0) {
        for (const zip of result.zips_deleted) {
            appendLog('zip', prefix + 'ZIP deleted (redundant): ' + zip);
        }
    }

    if (result.moved && result.moved.length > 0) {
        for (const item of result.moved) {
            const typeTag = item.item_type === 'dir' ? '[DIR]' : '[FILE]';
            appendLog('move', `${prefix}${typeTag} ${item.raw_name} → ${item.cleaned_name} [${item.category}]`);
        }
    }

    if (result.skipped && result.skipped.length > 0) {
        for (const item of result.skipped) {
            appendLog('skip', `${prefix}[SKIP] ${item.cleaned_name} (${item.is_duplicate ? 'duplicate' : 'error'})`);
        }
    }

    if (result.library_zips_cleaned && result.library_zips_cleaned.length > 0) {
        for (const zip of result.library_zips_cleaned) {
            appendLog('zip', prefix + 'Library ZIP cleaned: ' + zip);
        }
    }

    if (result.errors && result.errors.length > 0) {
        for (const err of result.errors) {
            appendLog('error', prefix + 'Error: ' + err);
        }
    }

    // Summary
    const total = (result.moved || []).length + (result.skipped || []).length;
    if (total === 0 && (!result.zips_extracted || result.zips_extracted.length === 0)) {
        appendLog('info', prefix + 'Nothing to sync — source folder is empty or has no new items.');
    } else {
        appendLog('info', `${prefix}Summary: ${(result.moved || []).length} moved, ${(result.skipped || []).length} skipped, ${(result.zips_extracted || []).length} ZIPs processed.`);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Start
// ─────────────────────────────────────────────────────────────────────────────

init();

// ─────────────────────────────────────────────────────────────────────────────
// Category Editor
// ─────────────────────────────────────────────────────────────────────────────

let categoriesData = [];

async function loadCategories() {
    try {
        const resp = await fetch('/api/categories/config');
        const data = await resp.json();
        categoriesData = data.categories || [];
        renderCategories();
    } catch (err) {
        logger.error('Failed to load categories', { error: err.message });
    }
}

function renderCategories() {
    const container = document.getElementById('category-editor');

    if (categoriesData.length === 0) {
        container.innerHTML = '<p class="log-placeholder">No categories configured. Run setup or add categories.</p>';
        return;
    }

    let html = '';
    for (let i = 0; i < categoriesData.length; i++) {
        const cat = categoriesData[i];
        const isUncat = cat.name === 'Uncategorized';
        const keywords = (cat.keywords || []).join(', ');

        html += `<div class="cat-row" data-index="${i}">
            <div class="cat-row-header">
                <input type="text" class="cat-name-input" value="${escapeHtml(cat.name)}"
                       ${isUncat ? 'disabled' : ''}
                       onchange="renameCategoryAt(${i}, this.value)">
                ${isUncat ? '' : `<button class="btn-icon btn-delete" onclick="deleteCategoryAt(${i})" title="Delete category">✕</button>`}
            </div>
            <div class="cat-row-keywords">
                <input type="text" class="cat-keywords-input" value="${escapeHtml(keywords)}"
                       placeholder="Comma-separated keywords…"
                       onchange="updateKeywordsAt(${i}, this.value)">
            </div>
        </div>`;
    }

    container.innerHTML = html;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
              .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renameCategoryAt(index, newName) {
    if (!newName.trim()) return;
    categoriesData[index].name = newName.trim();
    saveCategories();
}

function updateKeywordsAt(index, value) {
    const keywords = value.split(',').map(k => k.trim()).filter(k => k.length > 0);
    categoriesData[index].keywords = keywords;
    saveCategories();
}

function deleteCategoryAt(index) {
    const cat = categoriesData[index];
    if (cat.name === 'Uncategorized') return;
    if (!confirm(`Delete category "${cat.name}"? Its contents will be moved to Uncategorized.`)) return;
    categoriesData.splice(index, 1);
    saveCategories();
}

function addCategory() {
    const name = prompt('New category name:');
    if (!name || !name.trim()) return;

    // Insert before Uncategorized
    const uncatIdx = categoriesData.findIndex(c => c.name === 'Uncategorized');
    const newCat = { name: name.trim(), keywords: [] };

    if (uncatIdx >= 0) {
        categoriesData.splice(uncatIdx, 0, newCat);
    } else {
        categoriesData.push(newCat);
    }

    saveCategories();
}

async function saveCategories() {
    try {
        const resp = await fetch('/api/categories/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ categories: categoriesData }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            logger.error('Failed to save categories', { error: err.error });
            appendLog('error', 'Category save failed: ' + (err.error || 'unknown'));
            return;
        }

        const data = await resp.json();
        categoriesData = data.categories || [];
        renderCategories();
    } catch (err) {
        logger.error('Failed to save categories', { error: err.message });
    }
}

// Load categories on page load (after init)
loadCategories();
