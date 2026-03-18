/* ═══════════════════════════════════════════════════════════════════════════
   ContextFlow - app.js
   Vanilla JS. All API calls via fetch(). Zero external dependencies.
   ═══════════════════════════════════════════════════════════════════════════ */

const BASE_URL = 'http://localhost:8000';

// ─── Example prompts ─────────────────────────────────────────────────────────

const EXAMPLES = {
  sales: `Haan bhai, demo toh dekhenge, but pricing thodi zyada lag rahi hai. Main apni team se baat karke batata hoon. SSO ke baare mein bhi clear nahi hai, competitor ke paas already hai. Let's reconnect sometime next week, I'll get back to you.`,
  support: `Rahul called back extremely frustrated. The API bug we promised to fix in 48 hours is still occurring, it has been 8 days now. He said "This is costing us real money, we process 5000+ shipments a day." He is now evaluating two other vendors and wants a call with our VP of Engineering by end of day or he will escalate to his CTO. He also mentioned that the workaround we suggested last time did not work at all.`,
  vague: `Had a quick call with the client. They said things are "looking good internally" and they will "circle back soon." When I asked about timeline they said "probably in the next few weeks" but could not confirm anything specific. No decision maker on the call. They mentioned budget might be an issue but were not sure. Said they would think about it and let us know.`,
};

const VALID_STATUSES = ['pending', 'fulfilled', 'vague', 'overdue', 'cancelled'];

// ─── DOM Elements ────────────────────────────────────────────────────────────

const $select         = document.getElementById('customer-select');
const $newFields      = document.getElementById('new-customer-fields');
const $newId          = document.getElementById('new-customer-id');
const $newName        = document.getElementById('new-customer-name');
const $saveCustomerBtn= document.getElementById('save-customer-btn');
const $saveError      = document.getElementById('save-customer-error');
const $textarea       = document.getElementById('interaction-input');
const $dateInput      = document.getElementById('interaction-date');
const $analyzeBtn     = document.getElementById('analyze-btn');
const $inlineError    = document.getElementById('inline-error');
const $outputPanel    = document.getElementById('output-panel');
const $emptyState     = document.getElementById('empty-state');
const $historyToggle  = document.getElementById('history-toggle');
const $historyPanel   = document.getElementById('history-panel');
const $historyContent = document.getElementById('history-content');
const $ctxPreview     = document.getElementById('context-preview');
const $ctxInter       = document.getElementById('ctx-interactions');
const $ctxCommit      = document.getElementById('ctx-commitments');
const $ctxRisk        = document.getElementById('ctx-risk');
const $pendingBanner  = document.getElementById('pending-banner');

// ─── State ───────────────────────────────────────────────────────────────────

let historyOpen = false;
let isLoading   = false;

// Set default date to today
const today = new Date().toISOString().split('T')[0];
$dateInput.value = today;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function escapeHTML(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.add('visible');
}

function hideError(el) {
  el.classList.remove('visible');
}

function getCustomer() {
  const val = $select.value;
  if (val === '__new__') {
    return {
      id: $newId.value.trim(),
      name: $newName.value.trim(),
    };
  }
  const opt = $select.options[$select.selectedIndex];
  return {
    id: val,
    name: opt.dataset.name || '',
  };
}

function statusClass(status) {
  return 'status-' + (status || 'pending');
}

function riskClass(level) {
  return 'risk-' + (level || 'low');
}

function confidencePercent(score) {
  return Math.round((score || 0) * 100) + '%';
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  } catch {
    return dateStr.substring(0, 10);
  }
}

/** Build an inline <select> for changing commitment status */
function buildStatusSelect(commitmentId, currentStatus) {
  let html = `<select class="status-select ${statusClass(currentStatus)}" data-commitment-id="${escapeHTML(commitmentId)}" data-prev-status="${escapeHTML(currentStatus)}">`;
  for (const s of VALID_STATUSES) {
    const sel = s === currentStatus ? ' selected' : '';
    html += `<option value="${s}"${sel}>${s.toUpperCase()}</option>`;
  }
  html += '</select>';
  return html;
}

/** Call backend to update a commitment's status */
async function updateCommitmentStatus(commitmentId, newStatus, selectEl) {
  const prevStatus = selectEl.dataset.prevStatus;
  try {
    const res = await fetch(`${BASE_URL}/update-commitment`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commitment_id: commitmentId, status: newStatus }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Update failed');
    }
    // Update styling
    selectEl.className = `status-select ${statusClass(newStatus)}`;
    selectEl.dataset.prevStatus = newStatus;
    // Flash success
    selectEl.style.outline = '2px solid #22c55e';
    setTimeout(() => { selectEl.style.outline = ''; }, 1200);
    // Refresh context preview if a customer is selected
    const cust = getCustomer();
    if (cust.id) loadContextPreview(cust.id);
  } catch (e) {
    // Revert and flash error
    selectEl.value = prevStatus;
    selectEl.style.outline = '2px solid #ef4444';
    setTimeout(() => { selectEl.style.outline = ''; }, 2000);
    console.error('Status update failed:', e.message);
  }
}

// ─── Load customers from API ─────────────────────────────────────────────────

async function loadCustomers(preserveSelection) {
  try {
    const previousValue = $select.value;
    const res = await fetch(`${BASE_URL}/customers`);
    if (!res.ok) return;
    const customers = await res.json();

    // Remove all existing options except "__new__"
    while ($select.options.length > 1) {
      $select.remove(0);
    }

    // Insert customers before the "New Customer" option
    const newOpt = $select.querySelector('option[value="__new__"]');
    for (const c of customers) {
      const opt = document.createElement('option');
      opt.value = c.customer_id;
      opt.dataset.name = c.customer_name;
      opt.textContent = c.customer_name;
      $select.insertBefore(opt, newOpt);
    }

    // Preserve previous selection if requested, otherwise select first
    if (preserveSelection && previousValue && previousValue !== '__new__') {
      $select.value = previousValue;
    } else if (customers.length > 0) {
      $select.value = customers[0].customer_id;
      loadContextPreview(customers[0].customer_id);
    }
  } catch {
    // Fallback: keep whatever is in the dropdown
  }
}

// Load customers on page init
loadCustomers();
loadPendingBanner();

// ─── Customer selector logic ─────────────────────────────────────────────────

$select.addEventListener('change', () => {
  const isNew = $select.value === '__new__';
  $newFields.classList.toggle('visible', isNew);
  hideError($saveError);

  // Clear output when switching customers
  $outputPanel.classList.remove('visible');
  $outputPanel.innerHTML = '';
  $emptyState.style.display = '';

  // Close history
  historyOpen = false;
  $historyPanel.classList.remove('visible');

  // Load context preview for existing customers
  if (!isNew) {
    loadContextPreview($select.value);
  } else {
    $ctxPreview.classList.remove('visible');
  }
});

// ─── Save Customer ───────────────────────────────────────────────────────────

$saveCustomerBtn.addEventListener('click', () => {
  hideError($saveError);
  const id   = $newId.value.trim();
  const name = $newName.value.trim();

  if (!id) {
    showError($saveError, 'Customer ID is required.');
    return;
  }
  if (!name) {
    showError($saveError, 'Customer Name is required.');
    return;
  }

  // Check if this customer ID already exists in the dropdown
  for (const opt of $select.options) {
    if (opt.value === id) {
      showError($saveError, 'A customer with this ID already exists.');
      return;
    }
  }

  // Add to dropdown
  const newOpt = document.createElement('option');
  newOpt.value = id;
  newOpt.dataset.name = name;
  newOpt.textContent = name;
  const newCustomerOpt = $select.querySelector('option[value="__new__"]');
  $select.insertBefore(newOpt, newCustomerOpt);

  // Select the new customer
  $select.value = id;
  $newFields.classList.remove('visible');
  $ctxPreview.classList.remove('visible');

  // Clear fields
  $newId.value = '';
  $newName.value = '';
});

// ─── Example buttons ─────────────────────────────────────────────────────────

document.querySelectorAll('.example-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.example;
    if (EXAMPLES[key]) {
      $textarea.value = EXAMPLES[key];
      $textarea.focus();
      hideError($inlineError);
    }
  });
});

// ─── Context Preview ─────────────────────────────────────────────────────────

async function loadContextPreview(customerId) {
  try {
    const res = await fetch(`${BASE_URL}/get-customer/${customerId}`);
    if (!res.ok) {
      $ctxPreview.classList.remove('visible');
      return;
    }
    const data = await res.json();
    const interactions = data.interactions || [];
    const commitments  = data.commitments || [];
    const openCount    = commitments.filter(c =>
      c.status === 'pending' || c.status === 'vague' || c.status === 'overdue'
    ).length;

    // Determine latest risk from most recent interaction
    let latestRisk = 'N/A';
    if (interactions.length > 0) {
      const latest = interactions[interactions.length - 1];
      const sentiment = latest.extracted?.sentiment;
      const intent = latest.extracted?.intent;
      if (sentiment === 'negative' || intent === 'not_interested') latestRisk = 'High';
      else if (sentiment === 'neutral' || intent === 'neutral') latestRisk = 'Med';
      else latestRisk = 'Low';
    }

    $ctxInter.textContent  = interactions.length;
    $ctxCommit.textContent = openCount;
    $ctxRisk.textContent   = latestRisk;
    $ctxPreview.classList.add('visible');
  } catch {
    $ctxPreview.classList.remove('visible');
  }
}

// ─── History toggle ──────────────────────────────────────────────────────────

$historyToggle.addEventListener('click', async () => {
  historyOpen = !historyOpen;
  $historyPanel.classList.toggle('visible', historyOpen);

  if (!historyOpen) return;

  const customer = getCustomer();
  if (!customer.id) {
    $historyContent.innerHTML = '<span style="color:#3f3f46;font-size:0.82rem;">Enter a customer ID first.</span>';
    return;
  }

  $historyContent.innerHTML = '<span style="color:#52525b;font-size:0.82rem;">Loading history...</span>';

  try {
    const res = await fetch(`${BASE_URL}/get-customer/${customer.id}`);
    if (!res.ok) throw new Error('Failed to load');
    const data = await res.json();

    const interactions = data.interactions || [];
    const commitments  = data.commitments || [];

    if (interactions.length === 0 && commitments.length === 0) {
      $historyContent.innerHTML = '<span style="color:#3f3f46;font-size:0.82rem;">No history found for this customer.</span>';
      return;
    }

    let html = '';

    // Timeline
    if (interactions.length > 0) {
      html += '<div class="history-timeline">';
      const sorted = [...interactions].reverse();
      for (const inter of sorted) {
        const date = formatDate(inter.timestamp);
        const intent = inter.extracted?.intent || 'N/A';
        const sentiment = inter.extracted?.sentiment || 'N/A';
        const snippet = escapeHTML((inter.raw_input || '').substring(0, 120));
        html += `
          <div class="history-entry">
            <div class="history-date">${date} / intent: ${escapeHTML(intent)} / sentiment: ${escapeHTML(sentiment)}</div>
            <div class="history-text">${snippet}${inter.raw_input && inter.raw_input.length > 120 ? '...' : ''}</div>
          </div>`;
      }
      html += '</div>';
    }

    // Commitments mini table
    if (commitments.length > 0) {
      html += '<div class="history-commitments-mini"><table>';
      html += '<thead><tr><th>Commitment</th><th>Owner</th><th>Status</th><th>Confidence</th></tr></thead><tbody>';
      for (const c of commitments) {
        const cId = c.commitment_id || '';
        html += `<tr>
          <td>${escapeHTML(c.description || 'N/A')}</td>
          <td>${escapeHTML(c.owner || 'N/A')}</td>
          <td>${cId ? buildStatusSelect(cId, c.status || 'pending') : `<span class="status-pill ${statusClass(c.status)}">${escapeHTML((c.status || '').toUpperCase())}</span>`}</td>
          <td class="confidence-text">${confidencePercent(c.confidence_score)}</td>
        </tr>`;
      }
      html += '</tbody></table></div>';
    }

    $historyContent.innerHTML = html;
  } catch {
    $historyContent.innerHTML = '<span style="color:#ef4444;font-size:0.82rem;">Failed to load customer history.</span>';
  }
});

// ─── Analyze ─────────────────────────────────────────────────────────────────

$analyzeBtn.addEventListener('click', async () => {
  if (isLoading) return;
  hideError($inlineError);

  // Capture customer BEFORE the async call so dropdown changes can't affect it
  const customer = getCustomer();
  const capturedCustomerId = customer.id;
  const capturedCustomerName = customer.name || '';
  const rawInput = $textarea.value.trim();

  // Validation
  if (!capturedCustomerId) {
    showError($inlineError, 'Please enter a Customer ID.');
    return;
  }
  if (!rawInput || rawInput.length < 10) {
    showError($inlineError, 'Interaction note is too short. Provide at least 10 characters.');
    return;
  }

  // Loading state
  isLoading = true;
  $analyzeBtn.classList.add('loading');
  $analyzeBtn.disabled = true;
  $emptyState.style.display = 'none';
  $outputPanel.classList.remove('visible');
  $outputPanel.innerHTML = '';

  try {
    const res = await fetch(`${BASE_URL}/add-interaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customer_id: capturedCustomerId,
        customer_name: capturedCustomerName,
        raw_input: rawInput,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error (${res.status})`);
    }

    const result = await res.json();
    renderOutput(result);

    // Clear the interaction textarea for next use
    $textarea.value = '';

    // Refresh context preview using captured ID, preserve selection in dropdown
    loadContextPreview(capturedCustomerId);
    loadCustomers(true);

  } catch (e) {
    $outputPanel.innerHTML = `
      <div class="output-card" style="border-color:rgba(239,68,68,0.3);">
        <div class="output-card-header">
          <span class="output-card-label" style="color:#ef4444;">Error</span>
        </div>
        <div class="output-card-body" style="color:#ef4444;">${escapeHTML(e.message)}</div>
      </div>`;
    $outputPanel.classList.add('visible');
  } finally {
    isLoading = false;
    $analyzeBtn.classList.remove('loading');
    $analyzeBtn.disabled = false;
  }
});

// ─── Render Output ───────────────────────────────────────────────────────────

function renderOutput(result) {
  const fo         = result.final_output   || {};
  const extracted  = result.extracted       || {};
  const reasoning  = result.context_reasoning || {};
  const commitments= result.all_commitments || [];

  const interactionDate = $dateInput.value ? formatDate($dateInput.value) : formatDate(new Date().toISOString());

  let html = '';

  // 1. Summary Card
  html += `
    <div class="output-card">
      <div class="output-card-header">
        <span class="output-card-label">Interaction Summary</span>
        <span class="output-card-date">${escapeHTML(interactionDate)}</span>
      </div>
      <div class="output-card-body">${escapeHTML(fo.summary || 'N/A')}</div>
      <div class="meta-tags">
        <span class="meta-tag">intent: ${escapeHTML(extracted.intent || 'N/A')}</span>
        <span class="meta-tag">sentiment: ${escapeHTML(extracted.sentiment || 'N/A')}</span>
        <span class="meta-tag">language: ${escapeHTML(extracted.language_detected || 'N/A')}</span>
      </div>
    </div>`;

  // 2. Context Insights
  const insights = fo.context_insights || [];
  const intentShift = reasoning.intent_shift;
  const shiftDesc   = reasoning.intent_shift_description || '';

  html += `<div class="output-card">
    <div class="output-card-header">
      <span class="output-card-label">Context Insights</span>
    </div>`;

  if (intentShift) {
    html += `<div class="intent-shift-badge visible">Intent Shift Detected${shiftDesc ? ' / ' + escapeHTML(shiftDesc) : ''}</div>`;
  }

  if (insights.length > 0) {
    html += '<ul class="insight-list">';
    for (const ins of insights) {
      html += `<li>${escapeHTML(ins)}</li>`;
    }
    html += '</ul>';
  } else {
    html += '<div style="color:#3f3f46;font-size:0.82rem;">No prior context available for this customer.</div>';
  }
  html += '</div>';

  // 3. Objections (if any)
  const objections = extracted.objections || [];
  if (objections.length > 0) {
    html += `<div class="output-card">
      <div class="output-card-header">
        <span class="output-card-label">Objections Raised</span>
      </div>
      <div class="objection-tags">`;
    for (const obj of objections) {
      html += `<span class="objection-tag">${escapeHTML(obj)}</span>`;
    }
    html += '</div></div>';
  }

  // 4. Commitments Table
  html += `<div class="output-card">
    <div class="output-card-header">
      <span class="output-card-label">Commitments and Follow-ups</span>
    </div>`;

  if (commitments.length > 0) {
    html += `<table class="commitments-table">
      <thead>
        <tr>
          <th>Description</th>
          <th>Owner</th>
          <th>Due Date</th>
          <th>Status</th>
          <th>Confidence</th>
        </tr>
      </thead>
      <tbody>`;

    for (const c of commitments) {
      const isVague  = c.status === 'vague';
      const rowClass = isVague ? 'vague-row' : '';
      const cId = c.commitment_id || '';
      html += `<tr class="${rowClass}">
        <td class="desc-cell">
          ${escapeHTML(c.description || 'N/A')}
          ${isVague && c.vague_reason ? `<span class="vague-reason">Vague: ${escapeHTML(c.vague_reason)}</span>` : ''}
        </td>
        <td>${escapeHTML(c.owner || 'N/A')}</td>
        <td>${escapeHTML(c.due_date || 'N/A')}</td>
        <td>${cId ? buildStatusSelect(cId, c.status || 'pending') : `<span class="status-pill ${statusClass(c.status)}">${escapeHTML((c.status || '').toUpperCase())}</span>`}</td>
        <td class="confidence-text">${confidencePercent(c.confidence_score)}</td>
      </tr>`;
    }

    html += '</tbody></table>';
  } else {
    html += '<div class="empty-commitments">No commitments detected in this interaction.</div>';
  }
  html += '</div>';

  // 5. Risk Level
  const riskLevel  = fo.risk_level || 'low';
  const riskReason = fo.risk_reason || '';
  html += `<div class="output-card">
    <div class="output-card-header">
      <span class="output-card-label">Risk Assessment</span>
    </div>
    <span class="risk-badge ${riskClass(riskLevel)}">${escapeHTML(riskLevel.toUpperCase())}</span>
    <div class="risk-reason">${escapeHTML(riskReason)}</div>
  </div>`;

  // 6. Recommended Next Steps
  const steps = fo.recommended_next_steps || [];
  html += `<div class="output-card">
    <div class="output-card-header">
      <span class="output-card-label">Recommended Next Steps</span>
    </div>`;

  if (steps.length > 0) {
    html += '<ol class="next-steps-list">';
    for (const step of steps) {
      html += `<li>${escapeHTML(step)}</li>`;
    }
    html += '</ol>';
  } else {
    html += '<div style="color:#3f3f46;font-size:0.82rem;">No next steps generated.</div>';
  }
  html += '</div>';

  $outputPanel.innerHTML = html;

  // Trigger reflow then show with transition
  void $outputPanel.offsetHeight;
  $outputPanel.classList.add('visible');
}

// ─── Event delegation for status dropdowns ───────────────────────────────────

function handleStatusChange(e) {
  if (!e.target.classList.contains('status-select')) return;
  const commitmentId = e.target.dataset.commitmentId;
  const newStatus = e.target.value;
  if (commitmentId) updateCommitmentStatus(commitmentId, newStatus, e.target);
}

$historyContent.addEventListener('change', handleStatusChange);
$outputPanel.addEventListener('change', handleStatusChange);

// ─── Pending Items Banner ────────────────────────────────────────────────────

async function loadPendingBanner() {
  try {
    const res = await fetch(`${BASE_URL}/pending-commitments`);
    if (!res.ok) return;
    const items = await res.json();

    if (!items || items.length === 0) {
      $pendingBanner.classList.remove('visible');
      return;
    }

    // Group by customer
    const grouped = {};
    for (const item of items) {
      const cid = item.customer_id || 'Unknown';
      if (!grouped[cid]) grouped[cid] = { name: item.customer_name || cid, items: [] };
      grouped[cid].items.push(item);
    }

    let html = `
      <div class="pending-banner-header">
        <span class="pending-banner-icon">⚠</span>
        <span class="pending-banner-title">You have ${items.length} pending item${items.length > 1 ? 's' : ''} requiring attention</span>
        <button class="pending-banner-close" id="pending-banner-close" type="button">✕</button>
      </div>
      <div class="pending-banner-body">`;

    for (const [cid, group] of Object.entries(grouped)) {
      html += `<div class="pending-group">`;
      html += `<div class="pending-group-title">${escapeHTML(group.name)}</div>`;
      for (const item of group.items) {
        const statusLabel = (item.status || 'pending').toUpperCase();
        html += `<div class="pending-item">
          <span class="pending-item-desc">${escapeHTML(item.description || 'N/A')}</span>
          <span class="status-pill ${statusClass(item.status)}">${escapeHTML(statusLabel)}</span>
        </div>`;
      }
      html += `</div>`;
    }

    html += '</div>';
    $pendingBanner.innerHTML = html;
    $pendingBanner.classList.add('visible');

    // Attach close handler
    document.getElementById('pending-banner-close')?.addEventListener('click', () => {
      $pendingBanner.classList.remove('visible');
    });
  } catch (e) {
    console.error('Failed to load pending banner:', e);
  }
}
