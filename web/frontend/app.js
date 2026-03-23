/* PocketPricer — frontend logic */
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let extractedItems = [];   // [{product, weight, length, qty, tonnage, is_sheet, matched}]
let currentCustomer = '';
let selectedCustomerId = null;
let allProducts = [];      // full product list from server

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  checkAuth();
  initTabs();
  fetchStatus();
  wireButtons();
  initCustomer();
});

// ── Auth ───────────────────────────────────────────────────────────────────────
async function checkAuth() {
  try {
    const res = await fetch('/me');
    if (res.status === 401) { window.location.href = '/login'; return; }
    const user = await res.json();
    document.getElementById('user-name').textContent = user.username;
    if (user.username === 'admin') {
      document.getElementById('admin-warning').classList.remove('hidden');
    }
  } catch {
    window.location.href = '/login';
  }
}


// ── Tab switching ─────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
      if (btn.dataset.tab === 'history')  loadHistory();
      if (btn.dataset.tab === 'products') loadProducts();
    });
  });
}

// ── Status bar ────────────────────────────────────────────────────────────────
async function fetchStatus() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const res  = await fetch('/products');
    const data = await res.json();
    dot.className    = 'status-dot ready';
    text.textContent = `${data.count} products loaded`;
  } catch {
    dot.className    = 'status-dot error';
    text.textContent = 'offline';
  }
}

// ── Wire up all buttons ───────────────────────────────────────────────────────
function wireButtons() {
  // Quote tab
  document.getElementById('extract-btn').addEventListener('click', extractItems);
  document.getElementById('calculate-btn').addEventListener('click', calculateQuote);
  document.getElementById('clear-btn').addEventListener('click', clearAll);
  document.getElementById('copy-btn').addEventListener('click', copyResults);
  document.getElementById('apply-btn').addEventListener('click', applyToAll);

  // Products tab
  document.getElementById('add-product-btn').addEventListener('click', addProductRow);
  document.getElementById('product-search').addEventListener('input', filterProducts);

  // History tab
  document.getElementById('refresh-history-btn').addEventListener('click', loadHistory);

  // Auth
  document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
  });
}

// ── Customer autocomplete ─────────────────────────────────────────────────────
let _acTimer;

function initCustomer() {
  const input    = document.getElementById('customer-input');
  const dropdown = document.getElementById('customer-dropdown');

  input.addEventListener('input', () => {
    clearTimeout(_acTimer);
    const q = input.value.trim();
    if (!q) { closeDropdown(); selectedCustomerId = null; clearPriceChips(); return; }
    _acTimer = setTimeout(() => searchCustomers(q), 180);
  });

  // Close on outside click
  document.addEventListener('click', e => {
    if (!e.target.closest('.ac-wrap')) closeDropdown();
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDropdown();
  });
}

async function searchCustomers(query) {
  try {
    const res  = await fetch(`/customers?search=${encodeURIComponent(query)}`);
    const data = await res.json();
    renderDropdown(data.customers || [], query);
  } catch { /* silent */ }
}

function renderDropdown(customers, query) {
  const dropdown = document.getElementById('customer-dropdown');
  dropdown.innerHTML = '';

  if (customers.length) {
    customers.forEach(c => {
      const div = document.createElement('div');
      div.className   = 'ac-item';
      div.textContent = c.name;
      div.addEventListener('mousedown', e => {
        e.preventDefault();
        selectCustomer(c.id, c.name);
      });
      dropdown.appendChild(div);
    });
  }

  // Always offer "add new" if typed value isn't an exact match
  const exactMatch = customers.find(c => c.name.toLowerCase() === query.toLowerCase());
  if (!exactMatch) {
    const div = document.createElement('div');
    div.className   = 'ac-item ac-new';
    div.textContent = `Add "${query}" as new customer`;
    div.addEventListener('mousedown', e => {
      e.preventDefault();
      selectCustomer(null, query);
    });
    dropdown.appendChild(div);
  }

  dropdown.style.display = 'block';
}

async function selectCustomer(id, name) {
  selectedCustomerId = id;
  currentCustomer    = name;
  document.getElementById('customer-input').value = name;
  closeDropdown();

  if (id) {
    await loadCustomerPrices(id);
  } else {
    clearPriceChips();
  }
}

function closeDropdown() {
  document.getElementById('customer-dropdown').style.display = 'none';
}

async function loadCustomerPrices(customerId) {
  try {
    const res  = await fetch(`/customers/${customerId}/prices`);
    const data = await res.json();
    renderPrevQuotes(data.quotes || []);
  } catch { /* silent */ }
}

let _pqQuotes = [];  // cached quotes for the selected customer

function renderPrevQuotes(quotes) {
  _pqQuotes = quotes;
  const tabs     = document.getElementById('pq-tabs');
  const itemsRow = document.getElementById('pq-items-row');
  tabs.innerHTML     = '';
  itemsRow.innerHTML = '';
  itemsRow.classList.remove('visible');

  if (!quotes.length) return;

  quotes.forEach((q, i) => {
    const btn = document.createElement('button');
    btn.className   = 'pq-tab' + (i === 0 ? ' active' : '');
    btn.textContent = fmtDate(q.created_at);
    btn.addEventListener('click', () => {
      tabs.querySelectorAll('.pq-tab').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      showQuoteItems(q);
    });
    tabs.appendChild(btn);
  });

  // Auto-expand most recent
  showQuoteItems(quotes[0]);
}

function showQuoteItems(q) {
  const itemsRow = document.getElementById('pq-items-row');
  itemsRow.innerHTML = '';

  const items = (q.quote_data || []).filter(it => it.tonnage > 0);
  if (!items.length) { itemsRow.classList.remove('visible'); return; }

  items.forEach(item => {
    const chip = document.createElement('button');
    chip.className = 'pq-chip';
    const lengthStr = item.length ? ` · ${item.length}m` : '';
    chip.innerHTML = `
      <span class="pq-chip-product">${esc(item.product)}${esc(lengthStr)}</span>
      <span class="pq-chip-price">£${item.tonnage}/t</span>
    `;
    chip.title = 'Click to add this item to the quote';
    chip.addEventListener('click', () => addItemFromHistory(item));
    itemsRow.appendChild(chip);
  });

  itemsRow.classList.add('visible');
}

function addItemFromHistory(item) {
  // Build a new extracted item from historical data
  const newItem = {
    product:  item.product,
    weight:   item.weight   || 0,
    length:   item.length   || 0,
    qty:      item.qty      || 1,
    tonnage:  item.tonnage  || 0,
    is_sheet: item.is_sheet || false,
    matched:  true,
  };

  extractedItems.push(newItem);
  renderTable(extractedItems);
  toast(`Added ${item.product} to quote.`);
}

function clearPriceChips() {
  document.getElementById('pq-tabs').innerHTML     = '';
  document.getElementById('pq-items-row').innerHTML = '';
  document.getElementById('pq-items-row').classList.remove('visible');
}

function fmtDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

// ── Extract items from email ──────────────────────────────────────────────────
async function extractItems() {
  const emailText = document.getElementById('email-input').value.trim();
  if (!emailText) { toast('Paste a customer email first.'); return; }

  const btn     = document.getElementById('extract-btn');
  const btnText = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.btn-spinner');
  btnText.classList.add('hidden');
  spinner.classList.remove('hidden');
  btn.disabled = true;

  try {
    const res  = await fetch('/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_text: emailText }),
    });

    if (!res.ok) {
      const err = await res.json();
      toast(`Error: ${err.detail}`, true);
      return;
    }

    const data = await res.json();
    extractedItems = data.items || [];

    // Auto-fill customer field only if it's empty
    if (data.customer_name && !document.getElementById('customer-input').value.trim()) {
      selectCustomer(null, data.customer_name);
    }
    currentCustomer = document.getElementById('customer-input').value.trim() || data.customer_name || '';

    renderTable(extractedItems);

    const notFound  = data.not_found || [];
    const ambiguous = data.ambiguous || [];
    if (notFound.length || ambiguous.length) {
      const parts = [];
      if (ambiguous.length) parts.push(`${ambiguous.length} item(s) need clarification (see table)`);
      if (notFound.length)  parts.push(`${notFound.length} item(s) not found in product list`);
      setResults('⚠ ' + parts.join(' · ') + '.', true);
    } else {
      setResults('Items extracted — review the table, then click Calculate Quote.');
    }

  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  } finally {
    btnText.classList.remove('hidden');
    spinner.classList.add('hidden');
    btn.disabled = false;
  }
}

// ── Render items table ────────────────────────────────────────────────────────
function renderTable(items) {
  const tbody = document.getElementById('items-tbody');
  tbody.innerHTML = '';

  if (!items.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7" class="empty-msg">No items extracted.</td></tr>';
    return;
  }

  items.forEach((item, i) => {
    const tr = document.createElement('tr');
    const isSheet = item.is_sheet || false;
    tr.dataset.index     = i;
    tr.dataset.weight    = item.weight  || 0;
    tr.dataset.isSheet   = isSheet ? 'true' : 'false';
    tr.dataset.sheetArea = isSheet ? sheetAreaM2(item.product) : 0;
    if (item.ambiguous) tr.classList.add('row-ambiguous');
    if (isSheet) tr.classList.add('row-sheet');

    // Product cell
    let productCell;
    if (item.ambiguous && item.candidates?.length) {
      // Multiple matches — show inline selector
      const opts = item.candidates.map((c, ci) =>
        `<option value="${ci}">${esc(c.description)} (${c.weight.toFixed(2)} kg/m)</option>`
      ).join('');
      productCell = `
        <td class="col-product ambiguous-cell">
          <span class="ambig-icon" title="Clarification needed">⚠</span>
          <span class="ambig-label">${esc(item.requested || item.product)}</span>
          <select class="ambig-select" data-index="${i}">
            <option value="">— select type —</option>
            ${opts}
          </select>
        </td>`;
    } else if (item.not_found) {
      // No match — show customer's text with NOT FOUND badge
      productCell = `
        <td class="col-product not-found-cell">
          <span class="not-found-badge">NOT FOUND</span>
          <span class="not-found-text" title="Add this product via the Products tab">${esc(item.requested || item.product)}</span>
        </td>`;
    } else {
      // Matched — show DB description
      productCell = `<td class="col-product">${esc(item.product)}</td>`;
    }

    const weightCell = item.weight
      ? `${item.weight.toFixed(2)}<span class="weight-unit">${isSheet ? ' kg/m²' : ''}</span>`
      : '?';
    const lengthCell = isSheet
      ? `<td class="td-sheet-size" title="Priced per sheet — no length needed">per sheet</td>`
      : `<td><input class="cell-input" data-field="length" data-row="${i}" value="${item.length || ''}" placeholder="m" tabindex="${i * 3 + 2}"></td>`;

    tr.innerHTML = `
      <td class="td-num"><span class="row-num">${i + 1}</span><button class="btn-remove" title="Remove row">−</button></td>
      ${productCell}
      <td class="td-kgm">${weightCell}</td>
      <td><input class="cell-input" data-field="qty" data-row="${i}"     value="${item.qty     || 1}"   tabindex="${i * 3 + 1}"></td>
      ${lengthCell}
      <td><input class="cell-input" data-field="tonnage" data-row="${i}" value="${item.tonnage || ''}"  placeholder="£/t" tabindex="${i * 3 + 3}"></td>
      <td class="td-total line-total">—</td>
    `;

    // Disambiguation select handler
    const sel = tr.querySelector('.ambig-select');
    if (sel) {
      sel.addEventListener('change', () => {
        const ci = parseInt(sel.value);
        if (isNaN(ci)) return;
        const chosen = extractedItems[i].candidates[ci];
        extractedItems[i].product   = chosen.description;
        extractedItems[i].weight    = chosen.weight;
        extractedItems[i].is_sheet  = chosen.is_sheet || false;
        extractedItems[i].matched   = true;
        extractedItems[i].ambiguous = false;
        renderTable(extractedItems);
      });
    }

    tr.querySelector('.btn-remove').addEventListener('click', () => {
      extractedItems.splice(i, 1);
      renderTable(extractedItems);
    });

    tr.querySelectorAll('.cell-input').forEach(input => {
      input.addEventListener('input', () => recalcLine(tr));
      input.addEventListener('keydown', e => {
        const col = input.dataset.field;
        const row = parseInt(input.dataset.row);
        console.log(`Key pressed: ${e.key} | row=${row} col=${col}`);
        if (!['length', 'tonnage'].includes(col)) return;
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          document.querySelector(`.cell-input[data-field="${col}"][data-row="${row + 1}"]`)?.focus();
        } else if (e.key === 'ArrowUp' && row > 0) {
          e.preventDefault();
          document.querySelector(`.cell-input[data-field="${col}"][data-row="${row - 1}"]`)?.focus();
        } else if (e.key === 'ArrowRight' && col === 'length') {
          e.preventDefault();
          document.querySelector(`.cell-input[data-field="tonnage"][data-row="${row}"]`)?.focus();
        } else if (e.key === 'ArrowLeft' && col === 'tonnage') {
          e.preventDefault();
          document.querySelector(`.cell-input[data-field="length"][data-row="${row}"]`)?.focus();
        }
      });
    });

    tbody.appendChild(tr);

    if (item.length && item.tonnage) recalcLine(tr);
  });
}

// ── Sheet area helper ─────────────────────────────────────────────────────────
function sheetAreaM2(description) {
  // First two numbers are sheet dimensions in mm → convert to m²
  // e.g. '2500 x 1250 x 8mm HR Sheet' → 2.5 × 1.25 = 3.125 m²
  const nums = (description || '').match(/\d+(?:\.\d+)?/g) || [];
  if (nums.length >= 2) return (parseFloat(nums[0]) / 1000) * (parseFloat(nums[1]) / 1000);
  return 1;
}

// ── Recalculate a single row's line total (client-side) ───────────────────────
function recalcLine(tr) {
  const weight  = parseFloat(tr.dataset.weight)  || 0;
  const isSheet = tr.dataset.isSheet === 'true';
  const qty     = parseFloat(tr.querySelector('[data-field=qty]').value)     || 0;
  const tonnage = parseFloat(tr.querySelector('[data-field=tonnage]').value) || 0;

  let total = 0;
  if (isSheet) {
    // Sheet: weight is kg/m², multiply by sheet area to get total kg per sheet
    const area = parseFloat(tr.dataset.sheetArea) || 1;
    if (weight && tonnage && qty) {
      total = (weight * area * qty * tonnage) / 1000;
    }
  } else {
    const length = parseFloat(tr.querySelector('[data-field=length]').value) || 0;
    if (weight && tonnage && length) {
      total = (weight * tonnage / 1000) * length * qty;
    }
  }

  const cell = tr.querySelector('.line-total');
  cell.textContent = total > 0 ? `£${total.toFixed(2)}` : '—';
}

// ── Inline product search (for approximate match rejection) ───────────────────
async function showProductSearch(tr, itemIndex) {
  if (!allProducts.length) {
    const res = await fetch('/products');
    allProducts = (await res.json()).products || [];
  }
  const td = tr.querySelector('.approx-product-cell');
  td.innerHTML = `
    <div class="approx-search-wrap">
      <input class="approx-search-input" placeholder="Search products…" autocomplete="off">
      <div class="approx-search-results"></div>
    </div>`;
  const input   = td.querySelector('.approx-search-input');
  const results = td.querySelector('.approx-search-results');
  let matches   = [];
  input.focus();
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    if (!q) { results.style.display = 'none'; return; }
    matches = allProducts
      .filter(p => p.description.toLowerCase().includes(q) || (p.code || '').toLowerCase().includes(q))
      .slice(0, 12);
    if (!matches.length) { results.style.display = 'none'; return; }
    results.innerHTML = matches.map((p, mi) =>
      `<div class="approx-result-item" data-mi="${mi}">
        <span class="approx-result-desc">${esc(p.description)}</span>
        <span class="approx-result-weight">${p.weight.toFixed(2)} kg/m</span>
      </div>`
    ).join('');
    results.style.display = 'block';
  });
  results.addEventListener('click', e => {
    const row = e.target.closest('.approx-result-item');
    if (!row) return;
    const p = matches[parseInt(row.dataset.mi)];
    const isSheet = (p.type || '').toLowerCase().includes('sheet');
    extractedItems[itemIndex] = {
      ...extractedItems[itemIndex],
      product: p.description, weight: p.weight,
      is_sheet: isSheet, match_type: 'exact',
      confirmed: true, matched: true, not_found: false, ambiguous: false,
    };
    renderTable(extractedItems);
  });
}

// ── Calculate Quote ───────────────────────────────────────────────────────────
async function calculateQuote() {
  const rows = document.querySelectorAll('#items-tbody tr[data-index]');
  if (!rows.length) { toast('Extract items first.'); return; }


  const customerName = document.getElementById('customer-input').value.trim();
  const fillTonnage  = parseFloat(document.getElementById('fill-tonnage').value) || 0;

  const items = Array.from(rows).map(tr => ({
    product: extractedItems[tr.dataset.index].product,
    qty:     parseFloat(tr.querySelector('[data-field=qty]').value)     || 1,
    length:  parseFloat(tr.querySelector('[data-field=length]').value)  || 0,
    tonnage: parseFloat(tr.querySelector('[data-field=tonnage]').value) || 0,
  }));

  try {
    const res = await fetch('/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        items,
        customer_name: customerName,
        tonnage_price: fillTonnage,
      }),
    });

    const data = await res.json();
    renderResults(data);

    // Refresh quote cards — use customer_id returned by the server
    const customerId = data.customer_id;
    if (customerId) {
      selectedCustomerId = customerId;
      await loadCustomerPrices(customerId);
    }

  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  }
}

// ── Render pricing results panel ──────────────────────────────────────────────
function renderResults(data) {
  const out = document.getElementById('results-output');
  out.innerHTML = '';

  const pad = 52;
  data.lines.forEach(line => {
    const span = document.createElement('span');
    if (line.error) {
      span.textContent = `  ${line.product.padEnd(pad)}  NOT FOUND\n`;
      span.style.color = 'var(--red)';
    } else {
      span.textContent = `  ${line.product.substring(0, pad).padEnd(pad)}  £${line.total.toFixed(2)}\n`;
    }
    out.appendChild(span);
  });

  out.appendChild(document.createTextNode('\n'));
  const totalSpan = document.createElement('span');
  totalSpan.className   = 'total-line';
  totalSpan.textContent = `  ${'TOTAL'.padEnd(pad)}  £${data.grand_total.toFixed(2)}\n`;
  out.appendChild(totalSpan);
}

// ── Apply fill values to all rows ─────────────────────────────────────────────
function applyToAll() {
  const fillLen = document.getElementById('fill-length').value.trim();
  const fillTon = document.getElementById('fill-tonnage').value.trim();

  const rows = document.querySelectorAll('#items-tbody tr[data-index]');
  if (!rows.length) { toast('Extract items first.'); return; }

  rows.forEach(tr => {
    if (fillLen) tr.querySelector('[data-field=length]').value  = fillLen;
    if (fillTon) tr.querySelector('[data-field=tonnage]').value = fillTon;
    recalcLine(tr);
  });
}

// ── Clear all ─────────────────────────────────────────────────────────────────
function clearAll() {
  document.getElementById('email-input').value    = '';
  document.getElementById('customer-input').value = '';
  document.getElementById('fill-length').value    = '';
  document.getElementById('fill-tonnage').value   = '';
  document.getElementById('items-tbody').innerHTML =
    '<tr class="empty-row"><td colspan="7" class="empty-msg">Extract items from an email to begin.</td></tr>';
  setResults('');
  clearPriceChips();
  extractedItems     = [];
  currentCustomer    = '';
  selectedCustomerId = null;
}

function setResults(text, isWarning = false) {
  const el = document.getElementById('results-output');
  el.textContent = text;
  el.style.color = isWarning ? '#B45309' : '';
}

// ── Copy to clipboard ─────────────────────────────────────────────────────────
function copyResults() {
  const text = document.getElementById('results-output').textContent.trim();
  if (!text) { toast('Nothing to copy.'); return; }
  navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard.'));
}

// ═══════════════════════════════════════════════════════════════════════════════
// ── PRODUCTS TAB ──────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

async function loadProducts() {
  const tbody = document.getElementById('products-tbody');
  tbody.innerHTML = '<tr class="empty-row"><td colspan="6" class="empty-msg">Loading…</td></tr>';

  try {
    const res  = await fetch('/products');
    const data = await res.json();
    allProducts = data.products || [];
    renderProducts(allProducts);
  } catch (e) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6" class="empty-msg">Failed to load products.</td></tr>';
  }
}

function filterProducts() {
  const q = document.getElementById('product-search').value.toLowerCase();
  if (!q) { renderProducts(allProducts); return; }
  const filtered = allProducts.filter(p =>
    p.code.toLowerCase().includes(q) ||
    p.description.toLowerCase().includes(q) ||
    (p.type || '').toLowerCase().includes(q)
  );
  renderProducts(filtered);
}

function renderProducts(products) {
  const tbody = document.getElementById('products-tbody');
  tbody.innerHTML = '';

  if (!products.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6" class="empty-msg">No products found.</td></tr>';
    return;
  }

  products.forEach((p, i) => {
    tbody.appendChild(makeProductRow(p, i + 1));
  });
}

function makeProductRow(p, rowNum) {
  const tr = document.createElement('tr');
  tr.dataset.idx = p.idx;
  tr.innerHTML = `
    <td class="td-num">${rowNum}</td>
    <td style="font-family:var(--font-num);font-size:12px">${esc(p.code)}</td>
    <td>${esc(p.description)}</td>
    <td class="td-kgm">${p.weight.toFixed(3)}</td>
    <td style="color:var(--text-muted);font-size:12px">${esc(p.type || '')}</td>
    <td style="text-align:right">
      <button class="btn btn-ghost btn-sm" data-action="edit">Edit</button>
      <button class="btn btn-ghost btn-sm" data-action="delete" style="color:var(--red);margin-left:4px">Del</button>
    </td>
  `;
  tr.querySelector('[data-action=edit]').addEventListener('click',   () => editProductRow(tr, p));
  tr.querySelector('[data-action=delete]').addEventListener('click', () => deleteProduct(p.idx, tr));
  return tr;
}

function editProductRow(tr, p) {
  const idx = p.idx;
  tr.innerHTML = `
    <td class="td-num" style="color:var(--accent)">✎</td>
    <td><input class="prod-edit-input" data-f="code"        value="${esc(p.code)}"></td>
    <td><input class="prod-edit-input" data-f="description" value="${esc(p.description)}" style="width:100%"></td>
    <td><input class="prod-edit-input" data-f="weight"      value="${p.weight}" style="width:70px"></td>
    <td><input class="prod-edit-input" data-f="type"        value="${esc(p.type || '')}" style="width:60px"></td>
    <td style="text-align:right">
      <button class="btn btn-primary btn-sm" data-action="save">Save</button>
      <button class="btn btn-ghost btn-sm"   data-action="cancel" style="margin-left:4px">Cancel</button>
    </td>
  `;
  tr.querySelector('[data-action=save]').addEventListener('click',   () => saveProductRow(tr, idx));
  tr.querySelector('[data-action=cancel]').addEventListener('click', () => loadProducts());
  tr.querySelector('[data-f=code]').focus();
}

async function saveProductRow(tr, idx) {
  const code        = tr.querySelector('[data-f=code]').value.trim();
  const description = tr.querySelector('[data-f=description]').value.trim();
  const weight      = parseFloat(tr.querySelector('[data-f=weight]').value) || 0;
  const type        = tr.querySelector('[data-f=type]').value.trim();

  if (!code || !description) { toast('Code and description are required.', true); return; }

  const isNew  = idx === -1;
  const url    = isNew ? '/products' : `/products/${idx}`;
  const method = isNew ? 'POST'      : 'PUT';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, description, weight, type }),
    });
    if (!res.ok) { const e = await res.json(); toast(`Error: ${e.detail}`, true); return; }
    toast(isNew ? 'Product added.' : 'Product updated.');
    await loadProducts();
    await fetchStatus();
  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  }
}

async function deleteProduct(idx, tr) {
  if (!confirm('Delete this product?')) return;
  try {
    const res = await fetch(`/products/${idx}`, { method: 'DELETE' });
    if (!res.ok) { const e = await res.json(); toast(`Error: ${e.detail}`, true); return; }
    toast('Product deleted.');
    await loadProducts();
    await fetchStatus();
  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  }
}

function addProductRow() {
  const tbody = document.getElementById('products-tbody');

  // Remove "empty" placeholder if present
  const empty = tbody.querySelector('.empty-row');
  if (empty) empty.remove();

  // Don't add a second new-row if one already exists
  if (tbody.querySelector('[data-idx="-1"]')) return;

  const tr = document.createElement('tr');
  tr.dataset.idx = -1;
  tr.innerHTML = `
    <td class="td-num" style="color:var(--green)">+</td>
    <td><input class="prod-edit-input" data-f="code"        placeholder="e.g. UC203"></td>
    <td><input class="prod-edit-input" data-f="description" placeholder="Description" style="width:100%"></td>
    <td><input class="prod-edit-input" data-f="weight"      placeholder="kg/m" style="width:70px"></td>
    <td><input class="prod-edit-input" data-f="type"        placeholder="type" style="width:60px"></td>
    <td style="text-align:right">
      <button class="btn btn-primary btn-sm" data-action="save">Save</button>
      <button class="btn btn-ghost btn-sm"   data-action="cancel" style="margin-left:4px">Cancel</button>
    </td>
  `;
  tr.querySelector('[data-action=save]').addEventListener('click',   () => saveProductRow(tr, -1));
  tr.querySelector('[data-action=cancel]').addEventListener('click', () => loadProducts());
  tbody.prepend(tr);
  tr.querySelector('[data-f=code]').focus();
}

// ═══════════════════════════════════════════════════════════════════════════════
// ── HISTORY TAB ───────────────────────────────────────────────────────────────
// ═══════════════════════════════════════════════════════════════════════════════

async function loadHistory() {
  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = '<tr class="empty-row"><td colspan="5" class="empty-msg">Loading…</td></tr>';

  try {
    const res     = await fetch('/history');
    const data    = await res.json();
    const entries = data.entries || [];

    if (!entries.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5" class="empty-msg">No quotes yet.</td></tr>';
      return;
    }

    tbody.innerHTML = '';
    entries.forEach(entry => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-family:var(--font-num);font-size:11px;color:var(--text-muted)">${entry.timestamp.replace('T', '  ')}</td>
        <td>${esc(entry.customer || '—')}</td>
        <td style="color:var(--text-muted)">${entry.items.length}</td>
        <td class="history-total">£${entry.total.toFixed(2)}</td>
        <td style="text-align:right;white-space:nowrap">
          <button class="btn btn-ghost btn-sm" data-action="reload">Reload</button>
          <button class="btn btn-ghost btn-sm" data-action="rename" style="margin-left:4px">Rename</button>
          <button class="btn btn-ghost btn-sm" data-action="delete" style="margin-left:4px;color:var(--red)">Del</button>
        </td>
      `;
      tr.querySelector('[data-action=reload]').addEventListener('click',  () => reloadHistoryEntry(entry));
      tr.querySelector('[data-action=rename]').addEventListener('click',  () => renameQuote(entry));
      tr.querySelector('[data-action=delete]').addEventListener('click',  () => deleteQuote(entry.id, tr));
      tbody.appendChild(tr);
    });

  } catch (e) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="5" class="empty-msg">Failed to load history.</td></tr>';
  }
}

async function renameQuote(entry) {
  const newName = prompt('Rename quote:', entry.customer || '');
  if (newName === null) return;  // cancelled
  const name = newName.trim() || entry.customer;

  try {
    const res = await fetch(`/history/${entry.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    if (!res.ok) { const e = await res.json(); toast(`Error: ${e.detail}`, true); return; }
    toast('Quote renamed.');
    loadHistory();
  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  }
}

async function deleteQuote(id, tr) {
  if (!confirm('Delete this quote from history?')) return;
  try {
    const res = await fetch(`/history/${id}`, { method: 'DELETE' });
    if (!res.ok) { const e = await res.json(); toast(`Error: ${e.detail}`, true); return; }
    tr.remove();
    toast('Quote deleted.');
  } catch (e) {
    toast(`Request failed: ${e.message}`, true);
  }
}

function reloadHistoryEntry(entry) {
  // Switch to Quote tab
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
  document.querySelector('[data-tab=email]').classList.add('active');
  document.getElementById('tab-email').classList.add('active');

  currentCustomer = entry.customer;
  extractedItems  = entry.items.map(it => ({
    product:  it.product,
    weight:   it.weight || 0,
    length:   it.length,
    qty:      it.qty,
    tonnage:  it.tonnage,
    is_sheet: false,
    matched:  true,
  }));

  renderTable(extractedItems);
  renderResults({
    lines: entry.items.map(it => ({ product: it.product, total: it.total })),
    grand_total: entry.total,
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

let toastTimer;
function toast(msg, isError = false) {
  let el = document.querySelector('.toast');
  if (!el) {
    el = document.createElement('div');
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.borderColor = isError ? 'var(--red)' : 'var(--border)';
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2400);
}
