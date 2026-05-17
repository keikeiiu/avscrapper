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
    ingest:       {fields: [{name:'source',label:'Source dir',type:'text',def:'downloads/'},{name:'yes',label:'Auto-confirm',type:'check'}]},
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

// ── Helpers ────────────────────────
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s) { return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function trunc(s, n) { return s.length > n ? s.slice(0, n) + '...' : s; }
