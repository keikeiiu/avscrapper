/* AV Scraper Web GUI — frontend logic. Vanilla JS, no dependencies. */

// ── Shared State ──────────────────
let currentSession = null;
let currentEventSource = null;

// ── SSE Streaming ──────────────────
function connectSSE(session, onLine, onDone) {
  if (currentEventSource) currentEventSource.close();
  const es = new EventSource('/api/stream?session=' + session);
  currentEventSource = es;
  es.onmessage = function(e) {
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') onLine(msg.line);
    else if (msg.type === 'done') { onDone(msg.code); es.close(); currentEventSource = null; }
  };
  es.onerror = function() { if (es.readyState === EventSource.CLOSED) currentEventSource = null; };
  return es;
}

function logPanel(id) { return document.getElementById(id); }

function colorizeLine(line) {
  if (/error|fail|traceback/i.test(line)) return '<span class="log-red">' + esc(line) + '</span>';
  if (/done:|OK|success|completed|scraped/i.test(line)) return '<span class="log-green">' + esc(line) + '</span>';
  if (/404|skip|not found/i.test(line)) return '<span class="log-yellow">' + esc(line) + '</span>';
  return esc(line);
}

function appendLog(panel, line) {
  const div = document.createElement('div');
  div.innerHTML = colorizeLine(line);
  panel.appendChild(div);
  panel.scrollTop = panel.scrollHeight;
}

function clearLog(panel) { panel.innerHTML = ''; }

// ── Toast Notifications ────────────
function showToast(msg, type) {
  type = type || '';
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(function() { el.remove(); }, 4000);
}

// ── Action Runner ──────────────────
async function startAction(name, params, logEl, statusEl, spinnerEl, btnEl) {
  clearLog(logEl);
  if (statusEl) statusEl.textContent = '';
  if (spinnerEl) spinnerEl.style.display = 'inline';

  const form = new FormData();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== false) form.append(k, v);
  }

  const resp = await fetch('/api/action/' + name, { method: 'POST', body: form });
  const data = await resp.json();
  if (data.error) {
    appendLog(logEl, '[ERROR] ' + data.error);
    if (spinnerEl) spinnerEl.style.display = 'none';
    return;
  }

  currentSession = data.session;
  showToast('Started: ' + name.replace(/_/g, ' '), '');
  if (statusEl) statusEl.innerHTML = '<span class="badge accent">Session: ' + data.session + '</span>';

  connectSSE(data.session,
    function(line) { appendLog(logEl, line); },
    function(code) {
      appendLog(logEl, code === 0 ? '-- DONE (success) --' : '-- DONE (exit code ' + code + ') --');
      if (spinnerEl) spinnerEl.style.display = 'none';
      if (statusEl) statusEl.innerHTML = '<span class="badge ' + (code === 0 ? 'green' : 'red') + '">' + (code === 0 ? 'Completed' : 'Failed') + '</span>';
      if (btnEl) { btnEl.classList.remove('running'); btnEl.disabled = false; }
      resetQuickButtons();
      currentSession = null;
      showToast((code === 0 ? 'Completed' : 'Failed') + ': ' + name.replace(/_/g, ' '), code === 0 ? 'success' : 'error');
      setTimeout(refreshStats, 1000);
    }
  );
}

async function stopAction() {
  if (!currentSession) return;
  await fetch('/api/action/_/stop', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session: currentSession })
  });
  if (currentEventSource) currentEventSource.close();
  currentSession = null;
  resetQuickButtons();
}

// ── Actions Page ───────────────────
function updateForm() {
  const sel = document.getElementById('action-select').value;
  const div = document.getElementById('action-params');
  const btn = document.getElementById('run-btn');
  btn.disabled = !sel;
  if (!sel) { div.innerHTML = ''; return; }

  const specs = {
    ingest:       {fields: [{name:'source',label:'Source dir (optional)',type:'text'},{name:'yes',label:'Auto-confirm',type:'check'}]},
    scrape_fc2:   {fields: [{name:'ids',label:'CIDs (optional)',type:'text'},{name:'delay',label:'Delay',type:'text',def:'5-20'},{name:'flagged',label:'Flagged only',type:'check'},{name:'retry_errors',label:'Retry errors',type:'check'}]},
    scrape_jav:   {fields: [{name:'ids',label:'CIDs (optional)',type:'text'},{name:'delay',label:'Delay',type:'text',def:'5-20'},{name:'flagged',label:'Flagged only',type:'check'},{name:'retry_errors',label:'Retry errors',type:'check'}]},
    enrich_fc2:   {fields: [{name:'ids',label:'CIDs (optional)',type:'text'}]},
    enrich_jav:   {fields: [{name:'ids',label:'CIDs (optional)',type:'text'}]},
    reorganize:   {fields: [{name:'ids',label:'CIDs (optional)',type:'text'},{name:'dry_run',label:'Dry run',type:'check'}]},
    audit:        {fields: []},
    flag_fc2:     {fields: [{name:'ids',label:'CIDs (required)',type:'text'}]},
    flag_jav:     {fields: [{name:'ids',label:'CIDs (required)',type:'text'}]},
  };

  const spec = specs[sel];
  let html = '';
  for (const f of spec.fields) {
    if (f.type === 'check')
      html += '<div class="form-row"><label></label><label style="min-width:auto"><input type="checkbox" name="' + f.name + '" id="p-' + f.name + '"> ' + f.label + '</label></div>';
    else
      html += '<div class="form-row"><label>' + f.label + '</label><input type="text" name="' + f.name + '" id="p-' + f.name + '" value="' + (f.def || '') + '" style="min-width:300px"></div>';
  }
  div.innerHTML = html;
}

async function runAction() {
  const sel = document.getElementById('action-select').value;
  if (!sel) return;
  const params = {};
  document.querySelectorAll('#action-params [name]').forEach(el => {
    if (el.type === 'checkbox') params[el.name] = el.checked;
    else params[el.name] = el.value;
  });
  await startAction(sel, params, logPanel('action-log'), document.getElementById('action-status'), document.getElementById('action-spinner'));
}

// ── Dashboard Quick Actions ───────
function resetQuickButtons() {
  document.querySelectorAll('#quick-btns .btn').forEach(function(b) {
    b.classList.remove('running', 'primary');
    b.disabled = false;
  });
}

async function runQuickBtn(btn) {
  if (btn.disabled) return;
  const action = btn.dataset.action;
  const params = JSON.parse(btn.dataset.params);
  resetQuickButtons();
  btn.classList.add('running');
  document.querySelectorAll('#quick-btns .btn').forEach(function(b) { if (b !== btn) b.disabled = true; });
  document.getElementById('quick-spinner').style.display = 'inline';
  document.getElementById('quick-status').innerHTML = '';
  clearLog(logPanel('quick-log'));
  await startAction(action, params, logPanel('quick-log'), document.getElementById('quick-status'), document.getElementById('quick-spinner'), btn);
}

// ── Dashboard Stats ───────────────
async function refreshStats() {
  try {
    const resp = await fetch('/api/db/summary');
    const s = await resp.json();
    const cards = document.getElementById('stats-cards').querySelectorAll('.card');
    cards[0].querySelector('.value').textContent = s.fc2_total;
    cards[1].querySelector('.value').textContent = s.jav_total;
    cards[2].querySelector('.value').textContent = s.fc2_pending + s.jav_pending;
    cards[3].querySelector('.value').textContent = s.fc2_errors + s.jav_errors;
    // Pending detail badge
    const detail = document.getElementById('pending-detail');
    const parts = [];
    if (s.fc2_pending > 0) parts.push(s.fc2_pending + ' FC2');
    if (s.jav_pending > 0) parts.push(s.jav_pending + ' JAV');
    const fc2_f = s.fc2_errors, jav_f = s.fc2_errors;
    if (fc2_f + jav_f > 0) parts.push((fc2_f + jav_f) + ' flagged');
    detail.textContent = parts.join(' + ') || '';
    // Nav badge
    const badge = document.getElementById('nav-pending-badge');
    if (badge) badge.style.display = (s.fc2_pending + s.jav_pending + s.fc2_errors + s.jav_errors) > 0 ? '' : 'none';
  } catch(e) {}
}
if (document.getElementById('stats-cards')) { refreshStats(); setInterval(refreshStats, 30000); }

// ── DB Browser ─────────────────────
let currentTable = '';
let currentSort = { key: null, dir: 1 };
let currentPage = 1;
let columnVisibility = {};

function loadColVis() {
  try { columnVisibility = JSON.parse(localStorage.getItem('avscraper_columns') || '{}'); } catch(e) { columnVisibility = {}; }
}
function saveColVis() { localStorage.setItem('avscraper_columns', JSON.stringify(columnVisibility)); }
loadColVis();

function selectTable(name) {
  currentTable = name;
  currentPage = 1;
  document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
  document.querySelectorAll('.tab-btn').forEach(function(b) {
    if (b.textContent.toLowerCase().includes(name.replace(/_/g, ' '))) b.classList.add('active');
  });
  const isEntries = name.includes('entries');
  document.getElementById('db-status-filter').style.display = isEntries ? '' : 'none';
  document.getElementById('db-source-filter').style.display = isEntries ? '' : 'none';
  document.getElementById('bulk-flag-btn').style.display = isEntries ? '' : 'none';
  loadTable();
  buildColumnMenu();
}

function resetAndLoad() { currentPage = 1; loadTable(); }

async function loadTable() {
  if (!currentTable) return;
  try {
    const status = document.getElementById('db-status-filter').value;
    const source = document.getElementById('db-source-filter').value;
    const search = document.getElementById('db-search').value.trim();
    const perPage = document.getElementById('db-per-page').value;

    let url = '/api/db/table/' + currentTable + '?page=' + currentPage + '&per_page=' + perPage;
    if (status) url += '&status=' + encodeURIComponent(status);
    if (source) url += '&source=' + encodeURIComponent(source);
    if (search) url += '&search=' + encodeURIComponent(search);

    const resp = await fetch(url);
    const data = await resp.json();
    if (data.error) { document.getElementById('db-table').innerHTML = '<span class="dim">Error: ' + data.error + '</span>'; return; }
    if (!data.rows || !data.rows.length) { document.getElementById('db-table').innerHTML = '<span class="dim">No rows found.</span>'; document.getElementById('db-pagination').style.display = 'none'; return; }

    const colVis = columnVisibility[currentTable] || {};
    const keys = Object.keys(data.rows[0]).filter(function(k) { return colVis[k] !== false; });

    let html = '<table><thead><tr><th class="cb"><input type="checkbox" id="select-all" onchange="toggleSelectAll(this)"></th>';
    for (const k of keys) {
      const arrow = currentSort.key === k ? (currentSort.dir === 1 ? ' ▲' : ' ▼') : '';
      html += '<th onclick="sortTable(\'' + escAttr(k) + '\')">' + k + '<span class="sort-arrow">' + arrow + '</span></th>';
    }
    html += '<th></th></tr></thead><tbody>';

    for (const row of data.rows) {
      const rowStatus = row.status || '';
      const rowClass = rowStatus ? 'row-' + rowStatus : '';
      const pk = row[Object.keys(row)[0]];
      html += '<tr class="' + rowClass + '" onclick="toggleDetail(\'' + escAttr(String(pk || '')) + '\', this)">';
      html += '<td class="cb" onclick="event.stopPropagation()"><input type="checkbox" class="row-cb" data-cid="' + escAttr(String(row.cid || pk || '')) + '" onchange="updateBulkBtn()"></td>';
      for (const k of keys) {
        let v = row[k];
        if (k === 'tags' || k === 'genres' || k === 'actors') v = '[json]';
        html += '<td title="' + escAttr(String(v || '')) + '">' + esc(trunc(String(v || ''), 40)) + '</td>';
      }
      html += '<td>';
      if (currentTable === 'fc2_entries') html += '<button class="btn sm danger" onclick="event.stopPropagation();flagOne(\'flag_fc2\',\'' + escAttr(String(row.cid || '')) + '\')">Flag</button>';
      else if (currentTable === 'jav_entries') html += '<button class="btn sm danger" onclick="event.stopPropagation();flagOne(\'flag_jav\',\'' + escAttr(String(row.cid || '')) + '\')">Flag</button>';
      html += '</td></tr>';
    }
    html += '</tbody></table>';
    document.getElementById('db-table').innerHTML = html;

    let pagHtml = '<span class="page-info">Showing ' + ((data.page - 1) * data.per_page + 1) + '-' + Math.min(data.page * data.per_page, data.total) + ' of ' + data.total + '</span>';
    pagHtml += '<button class="btn sm" onclick="goPage(' + (data.page - 1) + ')" ' + (data.page <= 1 ? 'disabled' : '') + '>← Prev</button>';
    pagHtml += '<span class="page-info">Page ' + data.page + ' of ' + data.pages + '</span>';
    pagHtml += '<button class="btn sm" onclick="goPage(' + (data.page + 1) + ')" ' + (data.page >= data.pages ? 'disabled' : '') + '>Next →</button>';
    document.getElementById('db-pagination').innerHTML = pagHtml;
    document.getElementById('db-pagination').style.display = '';
  } catch(e) {
    document.getElementById('db-table').innerHTML = '<span class="dim" style="color:var(--red)">Error loading: ' + esc(String(e)) + '</span>';
    console.error('loadTable error:', e);
  }
}

function goPage(p) { currentPage = p; loadTable(); }

function sortTable(key) {
  if (currentSort.key === key) currentSort.dir *= -1;
  else { currentSort.key = key; currentSort.dir = 1; }
  loadTable();
}

function toggleSelectAll(cb) {
  document.querySelectorAll('.row-cb').forEach(function(c) { c.checked = cb.checked; });
  updateBulkBtn();
}

function updateBulkBtn() {
  const count = document.querySelectorAll('.row-cb:checked').length;
  document.getElementById('bulk-flag-btn').textContent = 'Flag Selected (' + count + ')';
}

async function toggleDetail(pk, tr) {
  if (tr.classList.contains('expanded')) {
    tr.classList.remove('expanded');
    const panel = tr.nextElementSibling;
    if (panel && panel.classList.contains('detail-row')) panel.remove();
    return;
  }
  const resp = await fetch('/api/db/row/' + currentTable + '/' + encodeURIComponent(pk));
  const data = await resp.json();
  if (data.error) return;

  tr.classList.add('expanded');
  const detailRow = document.createElement('tr');
  detailRow.className = 'detail-row';
  let html = '<td colspan="100"><div class="detail-panel"><button class="detail-close" onclick="event.stopPropagation();closeDetail(this)">&times;</button><dl>';
  for (const [k, v] of Object.entries(data)) {
    let disp = String(v || '');
    if (Array.isArray(v)) disp = v.map(function(x) { return typeof x === 'object' ? x.name || JSON.stringify(x) : x; }).join(', ');
    html += '<dt>' + k + '</dt><dd>' + esc(trunc(disp, 200)) + '</dd>';
  }
  html += '</dl></div></td>';
  detailRow.innerHTML = html;
  tr.after(detailRow);
}

function closeDetail(btn) {
  const tr = btn.closest('tr.detail-row').previousElementSibling;
  if (tr) { tr.classList.remove('expanded'); btn.closest('tr.detail-row').remove(); }
}

async function flagOne(action, cid) {
  if (!confirm('Flag ' + cid + ' for re-scrape?')) return;
  await fetch('/api/action/' + action, { method: 'POST', body: new URLSearchParams({ ids: cid }) });
  showToast('Flagged: ' + cid, 'success');
  loadTable();
}

async function bulkFlag() {
  const cids = [];
  document.querySelectorAll('.row-cb:checked').forEach(function(c) { cids.push(c.dataset.cid); });
  if (!cids.length) return;
  if (!confirm('Flag ' + cids.length + ' entries for re-scrape?')) return;
  const action = currentTable === 'fc2_entries' ? 'flag_fc2' : 'flag_jav';
  await fetch('/api/action/' + action, { method: 'POST', body: new URLSearchParams({ ids: cids.join(',') }) });
  showToast('Flagged ' + cids.length + ' entries', 'success');
  loadTable();
}

// ── Column Visibility ─────────────
function buildColumnMenu() {
  const menu = document.getElementById('col-menu');
  menu.innerHTML = '';
  if (!currentTable) return;
  // Fetch one row to get column names
  fetch('/api/db/table/' + currentTable + '?page=1&per_page=1').then(function(r) { return r.json(); }).then(function(data) {
    if (!data.rows || !data.rows.length) return;
    const vis = columnVisibility[currentTable] || {};
    for (const k of Object.keys(data.rows[0])) {
      const checked = vis[k] !== false ? ' checked' : '';
      menu.innerHTML += '<label><input type="checkbox" ' + checked + ' onchange="toggleColumn(\'' + k + '\', this.checked)"> ' + k + '</label>';
    }
  });
}

function toggleColumn(col, visible) {
  if (!columnVisibility[currentTable]) columnVisibility[currentTable] = {};
  if (visible) delete columnVisibility[currentTable][col];
  else columnVisibility[currentTable][col] = false;
  saveColVis();
  loadTable();
}

function toggleColumnMenu() {
  const menu = document.getElementById('col-menu');
  menu.style.display = menu.style.display === 'none' ? '' : 'none';
  buildColumnMenu();
}

// ── Logs Page ──────────────────────
async function viewReport(name) {
  const contentEl = document.getElementById('report-content');
  try {
    const resp = await fetch('/api/report/' + encodeURIComponent(name));
    if (resp.ok) {
      const html = await resp.text();
      contentEl.innerHTML = html;
    } else {
      contentEl.innerHTML = '<span class="dim">Report not found.</span>';
    }
  } catch(e) {
    contentEl.innerHTML = '<span class="dim">Error loading report.</span>';
  }
}

// ── Pipeline ───────────────────────
var pipeStartTime = 0;
var pipeDoneCount = 0;
var pipeTotal = 7;

function runPipeline() {
  const btn = document.getElementById('run-pipeline-btn');
  if (btn.classList.contains('running')) return;
  btn.classList.add('running');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Running...';

  // Reset all nodes
  document.querySelectorAll('.pipe-node').forEach(function(n) {
    n.className = 'pipe-node waiting';
    n.querySelector('.pipe-node-result').textContent = '';
  });
  document.querySelectorAll('.pipe-connector').forEach(function(c) {
    c.classList.remove('done');
  });
  document.getElementById('pipe-log').innerHTML = '';
  document.getElementById('pipe-error-msg').style.display = 'none';
  document.getElementById('pipe-spinner').style.display = '';
  document.getElementById('pipeline-summary').style.display = '';
  pipeStartTime = Date.now();
  pipeDoneCount = 0;

  var params = {};
  if (document.getElementById('opt-dry-run').checked) params.dry_run = true;
  if (document.getElementById('opt-skip-scrape').checked) params.skip_scrape = true;
  if (document.getElementById('opt-skip-enrich').checked) params.skip_enrich = true;

  pipeTotal = 6 - (params.skip_scrape ? 2 : 0) - (params.skip_enrich ? 2 : 0);
  document.getElementById('pipe-progress').textContent = '0 / ' + pipeTotal + ' steps';

  var formData = new URLSearchParams();
  for (var k in params) { if (params[k]) formData.append(k, '1'); }

  fetch('/api/action/pipeline', { method: 'POST', body: formData })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) { showToast(data.error, 'error'); resetPipeBtn(); return; }
      pipeSSE(data.session);
    })
    .catch(function(e) { showToast('Failed to start: ' + e, 'error'); resetPipeBtn(); });
}

function pipeSSE(session) {
  if (window._pipeEvents) { window._pipeEvents.close(); }
  var es = new EventSource('/api/stream?session=' + session);
  window._pipeEvents = es;

  es.onmessage = function(e) {
    var msg = JSON.parse(e.data);
    var logEl = document.getElementById('pipe-log');

    if (msg.type === 'step_start') {
      setNodeState(msg.step, 'running');
      appendLog(logEl, '--- ' + msg.label + ' ---');
    } else if (msg.type === 'step_done') {
      setNodeState(msg.step, msg.code === 0 ? 'done' : 'error');
      pipeDoneCount++;
      updateSummary();
    } else if (msg.type === 'step_skip') {
      setNodeState(msg.step, 'skipped');
      pipeTotal--;
      updateSummary();
    } else if (msg.type === 'pipeline_error') {
      updateSummary(msg.label + ' failed');
    } else if (msg.type === 'done') {
      resetPipeBtn();
      es.close();
      window._pipeEvents = null;
      if (msg.code === 0) {
        showToast('Pipeline completed', 'success');
        setTimeout(refreshStats, 1000);
      } else {
        showToast('Pipeline failed', 'error');
      }
    } else if (msg.type === 'log' && logEl) {
      appendLog(logEl, msg.line);
    }
  };

  es.onerror = function() {
    es.close();
    window._pipeEvents = null;
    resetPipeBtn();
  };
}

function setNodeState(step, state) {
  var node = document.getElementById('node-' + step);
  if (!node) return;
  node.className = 'pipe-node ' + state;

  // Color the connector ABOVE this node
  var conn = document.getElementById('conn-' + step);
  if (conn && (state === 'done' || state === 'skipped')) {
    conn.classList.add('done');
  }
}

function updateSummary(errMsg) {
  var elapsed = Math.round((Date.now() - pipeStartTime) / 1000);
  var m = Math.floor(elapsed / 60);
  var s = elapsed % 60;
  document.getElementById('pipe-elapsed').textContent = (m ? m + 'm ' : '') + s + 's';
  document.getElementById('pipe-progress').textContent = pipeDoneCount + ' / ' + pipeTotal + ' steps';
  if (errMsg) {
    var el = document.getElementById('pipe-error-msg');
    el.textContent = errMsg;
    el.style.display = '';
  }
}

function resetPipeBtn() {
  var btn = document.getElementById('run-pipeline-btn');
  btn.classList.remove('running');
  btn.disabled = false;
  btn.innerHTML = '&#9654; Run Pipeline';
  document.getElementById('pipe-spinner').style.display = 'none';
}

// ── Browse Grid ─────────────────────
let browseState = {
  type: 'fc2',
  search: '',
  filters: {},
  sort: 'scraped_at',
  order: 'desc',
  page: 1,
  perPage: 48,
  total: 0,
  pages: 1,
  debounceTimer: null
};

function initBrowse() {
  if (!document.getElementById('browse-grid')) return;
  document.getElementById('browse-search').addEventListener('input', onBrowseSearch);
  document.getElementById('browse-sort-dir').textContent = browseState.order === 'desc' ? '↓' : '↑';
  loadFacets(browseState.type);
  loadBrowseGrid();
}

function selectBrowseType(type) {
  browseState.type = type;
  browseState.filters = {};
  browseState.page = 1;
  browseState.sort = 'scraped_at';
  browseState.order = 'desc';
  document.getElementById('browse-sort').value = 'scraped_at';
  document.getElementById('browse-sort-dir').textContent = '↓';
  document.getElementById('browse-search').value = '';
  document.querySelectorAll('#browse-tabs .tab-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.type === type);
  });
  loadFacets(type);
  loadBrowseGrid();
}

function loadFacets(type) {
  fetch('/api/db/facets/' + type)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) return;

      // Status dropdown
      var sel = document.getElementById('browse-status');
      sel.innerHTML = '<option value="">All Statuses</option>';
      for (var s in data.statuses) {
        if (s === 'null') continue;
        sel.innerHTML += '<option value="' + escAttr(s) + '">' + esc(s) + ' (' + data.statuses[s] + ')</option>';
      }

      // Show/hide type-specific filters
      var isJav = type === 'jav';
      document.getElementById('browse-studio').style.display = isJav ? '' : 'none';
      document.getElementById('browse-series').style.display = isJav ? '' : 'none';
      document.getElementById('browse-director').style.display = isJav ? '' : 'none';
      document.getElementById('browse-seller').style.display = isJav ? 'none' : '';
      document.getElementById('browse-actress').style.display = isJav ? 'none' : '';

      for (var i = 0; i < data.filters.length; i++) {
        var f = data.filters[i];
        var filterSel = document.getElementById('browse-' + f.field);
        if (!filterSel) continue;
        filterSel.innerHTML = '<option value="">All ' + f.label + 's</option>';
        for (var j = 0; j < f.values.length; j++) {
          filterSel.innerHTML += '<option value="' + escAttr(f.values[j].value) + '">' + esc(f.values[j].value) + ' (' + f.values[j].count + ')</option>';
        }
      }
    })
    .catch(function(e) { console.error('loadFacets error:', e); });
}

function loadBrowseGrid() {
  var url = '/api/db/browse?type=' + browseState.type +
    '&page=' + browseState.page +
    '&per_page=' + browseState.perPage +
    '&sort=' + browseState.sort +
    '&order=' + browseState.order;
  if (browseState.search) url += '&search=' + encodeURIComponent(browseState.search);
  for (var key in browseState.filters) {
    if (browseState.filters[key]) url += '&' + key + '=' + encodeURIComponent(browseState.filters[key]);
  }

  fetch(url)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        document.getElementById('browse-empty').style.display = '';
        document.getElementById('browse-grid').innerHTML = '';
        document.getElementById('browse-pagination').style.display = 'none';
        return;
      }

      browseState.total = data.total;
      browseState.pages = data.pages;
      browseState.page = data.page;

      if (!data.rows || !data.rows.length) {
        document.getElementById('browse-grid').innerHTML = '';
        document.getElementById('browse-empty').style.display = '';
        document.getElementById('browse-pagination').style.display = 'none';
      } else {
        document.getElementById('browse-empty').style.display = 'none';
        renderBrowseGrid(data);
        renderBrowsePagination();
      }
    })
    .catch(function(e) {
      console.error('loadBrowseGrid error:', e);
    });
}

function renderBrowseGrid(data) {
  var html = '';
  for (var i = 0; i < data.rows.length; i++) {
    html += renderPosterCard(data.rows[i], browseState.type);
  }
  document.getElementById('browse-grid').innerHTML = html;
}

function renderPosterCard(row, type) {
  var coverHtml;
  if (row.cover_url) {
    coverHtml = '<img src="' + escAttr(row.cover_url) + '" loading="lazy" referrerpolicy="no-referrer"' +
      ' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">' +
      '<div class="no-cover" style="display:none"><span>' + esc(row.cid || '') + '</span><span style="font-size:11px">No cover</span></div>';
  } else {
    coverHtml = '<div class="no-cover"><span>' + esc(row.cid || '') + '</span><span style="font-size:11px">No cover</span></div>';
  }

  var statusHtml = '';
  if (row.status && row.status !== 'scraped') {
    statusHtml = '<span class="status-badge badge ' + statusColor(row.status) + '">' + esc(row.status) + '</span>';
  }

  var ratingHtml = '';
  if (type === 'jav' && row.rating) {
    ratingHtml = '<span class="rating">&#9733; ' + parseFloat(row.rating).toFixed(1) + '</span>';
  }

  var filesHtml = '';
  if (row.file_count > 0) {
    filesHtml = '<span>' + row.file_count + ' file' + (row.file_count !== 1 ? 's' : '') + '</span>';
  }

  var durationHtml = '';
  if (row.duration_str) {
    durationHtml = '<span>' + esc(row.duration_str) + '</span>';
  } else if (row.duration) {
    durationHtml = '<span>' + esc(row.duration) + '</span>';
  }

  return '<div class="poster-card" onclick="openBrowseDetail(\'' + escAttr(row.cid || '') + '\')">' +
    '<div class="poster-cover">' + coverHtml + statusHtml + '</div>' +
    '<div class="poster-info">' +
      '<div class="card-title" title="' + escAttr(row.title || row.cid || '') + '">' + esc(row.title || row.cid || '') + '</div>' +
      '<div class="card-cid">' + esc(row.cid || '') + '</div>' +
      '<div class="card-meta">' + ratingHtml + filesHtml + durationHtml + '</div>' +
    '</div>' +
  '</div>';
}

function renderBrowsePagination() {
  var el = document.getElementById('browse-pagination');
  var s = browseState;
  var start = (s.page - 1) * s.perPage + 1;
  var end = Math.min(s.page * s.perPage, s.total);
  el.innerHTML =
    '<span class="page-info">' + start + '-' + end + ' of ' + s.total + '</span>' +
    '<button class="btn sm" onclick="goBrowsePage(' + (s.page - 1) + ')" ' + (s.page <= 1 ? 'disabled' : '') + '>← Prev</button>' +
    '<span class="page-info">Page ' + s.page + ' of ' + s.pages + '</span>' +
    '<button class="btn sm" onclick="goBrowsePage(' + (s.page + 1) + ')" ' + (s.page >= s.pages ? 'disabled' : '') + '>Next →</button>';
  el.style.display = '';
}

function onBrowseSearch() {
  clearTimeout(browseState.debounceTimer);
  browseState.debounceTimer = setTimeout(function() {
    browseState.search = document.getElementById('browse-search').value.trim();
    browseState.page = 1;
    loadBrowseGrid();
  }, 300);
}

function onBrowseFilterChange(field, value) {
  if (value) {
    browseState.filters[field] = value;
  } else {
    delete browseState.filters[field];
  }
  browseState.page = 1;
  renderActiveFilters();
  loadBrowseGrid();
}

function removeBrowseFilter(field) {
  delete browseState.filters[field];
  var sel = document.getElementById('browse-' + field);
  if (sel) sel.value = '';
  browseState.page = 1;
  renderActiveFilters();
  loadBrowseGrid();
}

function renderActiveFilters() {
  var html = '';
  for (var key in browseState.filters) {
    if (browseState.filters[key]) {
      html += '<span class="filter-chip">' + esc(key) + ': ' + esc(browseState.filters[key]) +
        '<span class="remove" onclick="removeBrowseFilter(\'' + escAttr(key) + '\')" title="Remove filter">&times;</span></span>';
    }
  }
  document.getElementById('filter-chips').innerHTML = html;
}

function onBrowseSortChange() {
  browseState.sort = document.getElementById('browse-sort').value;
  browseState.page = 1;
  loadBrowseGrid();
}

function toggleSortDir() {
  browseState.order = browseState.order === 'desc' ? 'asc' : 'desc';
  document.getElementById('browse-sort-dir').textContent = browseState.order === 'desc' ? '↓' : '↑';
  browseState.page = 1;
  loadBrowseGrid();
}

function goBrowsePage(p) {
  if (p < 1 || p > browseState.pages) return;
  browseState.page = p;
  loadBrowseGrid();
  document.getElementById('browse-grid').scrollIntoView({ behavior: 'smooth' });
}

function openBrowseDetail(cid) {
  var table = browseState.type + '_entries';
  fetch('/api/db/row/' + table + '/' + encodeURIComponent(cid))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) { showToast('Failed to load details', 'error'); return; }

      var coverHtml;
      if (data.cover_url) {
        coverHtml = '<img src="' + escAttr(data.cover_url) + '" class="modal-cover-img" referrerpolicy="no-referrer"' +
          ' onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">' +
          '<div class="modal-no-cover" style="display:none">' + esc(cid) + '</div>';
      } else {
        coverHtml = '<div class="modal-no-cover">' + esc(cid) + '</div>';
      }

      var statusHtml = '';
      if (data.status) {
        statusHtml = '<span class="status-badge badge ' + statusColor(data.status) + '">' + esc(data.status) + '</span>';
      }

      var dlHtml = '';
      var fields = ['full_number', 'title', 'studio', 'label', 'series', 'director',
                    'seller', 'actress', 'release_date', 'year', 'duration', 'runtime',
                    'rating', 'votes', 'region', 'source', 'mosaic', 'audit_status',
                    'scraped_at', 'last_audited', 'url', 'outline', 'plot', 'error_message'];
      var dtFields = ['release_date', 'scraped_at', 'last_audited'];
      for (var i = 0; i < fields.length; i++) {
        var v = data[fields[i]];
        if (v === null || v === undefined || v === '') continue;
        if (Array.isArray(v)) {
          v = v.map(function(x) { return typeof x === 'object' ? (x.name || JSON.stringify(x)) : x; }).join(', ');
        }
        var display = String(v);
        if (fields[i] === 'region') {
          display = display === 'chinese' ? 'Chinese' : (display === 'jav' ? 'Japanese' : display);
        }
        if (dtFields.indexOf(fields[i]) !== -1) {
          display = fmtDate(v);
        }
        if (fields[i] === 'url' && /^https?:\/\//.test(v)) {
          dlHtml += '<dt>' + fields[i] + '</dt><dd><a href="' + escAttr(String(v)) + '" target="_blank" rel="noopener">' + esc(display) + '</a></dd>';
        } else {
          dlHtml += '<dt>' + fields[i] + '</dt><dd>' + esc(display) + '</dd>';
        }
      }

      // File listing
      var filesHtml = '';
      var fileTable = browseState.type + '_files';
      if (data.file_count === undefined) {
        // fetch files separately if not included in detail
      }

      var modalHtml =
        '<button class="modal-close" onclick="closeBrowseDetail()">&times;</button>' +
        '<div class="modal-layout">' +
          coverHtml +
          '<div class="modal-details">' +
            '<h3>' + esc(data.title || data.cid || '') + '</h3>' +
            '<div class="modal-cid">' + esc(data.cid || '') + '</div>' +
            statusHtml +
            '<dl>' + dlHtml + '</dl>' +
          '</div>' +
        '</div>';

      document.getElementById('browse-modal-content').innerHTML = modalHtml;
      document.getElementById('browse-modal').style.display = '';
      document.body.style.overflow = 'hidden';

      // Fetch file listing in parallel
      fetch('/api/db/table/' + fileTable + '?search=' + encodeURIComponent(cid) + '&per_page=50')
        .then(function(r) { return r.json(); })
        .then(function(fdata) {
          if (fdata.rows && fdata.rows.length) {
            var ftable = '<div class="modal-files"><h4>Files (' + fdata.rows.length + ')</h4><table><thead><tr><th>Path</th><th>File</th><th>Size</th><th>Duration</th></tr></thead><tbody>';
            for (var fi = 0; fi < fdata.rows.length; fi++) {
              var fr = fdata.rows[fi];
              var fname = fr.file_path ? fr.file_path.split('/').pop().split('\\').pop() : '';
              var dir = fr.directory_path || (fr.file_path ? fr.file_path.substring(0, fr.file_path.lastIndexOf('/') !== -1 ? fr.file_path.lastIndexOf('/') : fr.file_path.lastIndexOf('\\')) : '-');
              var filePathEnc = escAttr(fr.file_path || '');
              var dirPathEnc = escAttr(dir || '');
              ftable += '<tr>' +
                '<td style="max-width:240px">' + (dir && dir !== '-' ? '<a href="#" class="file-link" data-path="' + dirPathEnc + '" onclick="openFilePath(this.dataset.path);return false" title="Open folder">' + esc(trunc(dir, 50)) + '</a>' : '-') + '</td>' +
                '<td>' + (fr.file_path ? '<a href="#" class="file-link" data-path="' + filePathEnc + '" onclick="openFilePath(this.dataset.path);return false" title="' + filePathEnc + '">' + esc(fname || fr.file_path || '-') + '</a>' : esc(fname || '-')) + '</td>' +
                '<td>' + (fr.file_size ? formatSize(fr.file_size) : '-') + '</td>' +
                '<td>' + (fr.duration_str || '-') + '</td></tr>';
            }
            ftable += '</tbody></table></div>';
            document.querySelector('#browse-modal-content .modal-layout').insertAdjacentHTML('beforeend', ftable);
          }
        });
    })
    .catch(function(e) { console.error('openBrowseDetail error:', e); });
}

function closeBrowseDetail() {
  document.getElementById('browse-modal').style.display = 'none';
  document.body.style.overflow = '';
}

function openFilePath(path) {
  fetch('/api/open-file?path=' + encodeURIComponent(path))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        showToast('Cannot open: ' + data.error, 'error');
      } else if (data.status === 'path_only') {
        // Docker/headless: no display, return the path for clipboard or manual use
        showToast('Path (Docker): ' + data.path, 'success');
      } else {
        showToast('Opened: ' + (data.path || path).split('/').pop(), 'success');
      }
    })
    .catch(function(e) { showToast('Failed to open file', 'error'); });
}

function statusColor(status) {
  switch (status) {
    case 'scraped': return 'green';
    case 'pending': return 'muted';
    case 'error': case 'login_required': return 'red';
    case '404': return 'orange';
    case 'flagged': return 'yellow';
    default: return 'muted';
  }
}

// ── Keyboard Shortcuts (Browse page) ──
document.addEventListener('keydown', function(e) {
  if (!document.getElementById('browse-grid')) return;
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
  var cards = document.querySelectorAll('#browse-grid .card');
  var focused = document.querySelector('#browse-grid .card.focused');
  var idx = focused ? Array.from(cards).indexOf(focused) : -1;
  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault(); focused && focused.classList.remove('focused');
    var next = idx < cards.length - 1 ? cards[idx + 1] : null;
    if (next) { next.classList.add('focused'); next.scrollIntoView({block:'nearest',behavior:'smooth'}); }
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault(); focused && focused.classList.remove('focused');
    var prev = idx > 0 ? cards[idx - 1] : cards[0];
    if (prev) { prev.classList.add('focused'); prev.scrollIntoView({block:'nearest',behavior:'smooth'}); }
  } else if (e.key === 'Enter' && focused) {
    e.preventDefault(); focused.click();
  } else if (e.key === 'f' && focused) {
    e.preventDefault(); var fl = focused.querySelector('[data-file]'); if (fl) fl.click();
  } else if (e.key === 'Escape') {
    var modal = document.querySelector('.modal-overlay'); if (modal) modal.remove();
  }
});

function formatSize(bytes) {
  if (!bytes) return '0 B';
  var units = ['B', 'KB', 'MB', 'GB', 'TB'];
  var i = 0;
  var size = bytes;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return size.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}
function fmtDate(s) {
  if (!s) return '';
  // Normalize ISO '2026-05-16T03:51:13' → '2026-05-16 03:51'
  var t = s.replace('T', ' ');
  // Drop seconds if present: '2026-05-16 03:51:13' → '2026-05-16 03:51'
  return t.replace(/(:\d{2})(:\d{2})$/, '$1');
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function trunc(s, n) { return s.length > n ? s.slice(0, n) + '...' : s; }
