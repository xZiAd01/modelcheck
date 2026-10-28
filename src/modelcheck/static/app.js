const $ = id => document.getElementById(id);
let token = sessionStorage.getItem('modelcheck-token');
let bundleId = null, review = null, samples = [], live = false, pollTimer = null, reviewRunning = false;
let renderedAction = '', announcementFrame = null;

function node(tag, text, cls) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (cls) element.className = cls;
  return element;
}
function announce(text) {
  cancelAnimationFrame(announcementFrame);
  $('status-message').textContent = '';
  announcementFrame = requestAnimationFrame(() => { $('status-message').textContent = text; });
}
function notice(text, error = false) {
  $('notice').textContent = text;
  $('notice').hidden = !text;
  if (error) $('error-message').textContent = text;
  else { $('error-message').textContent = ''; if (text) announce(text); }
}
function fieldError(id, message) {
  const error = new Error(message);
  error.field = id;
  return error;
}
function showError(error) {
  if (error.field && $(error.field)) {
    const input = $(error.field), message = $(error.field + '-error');
    input.setAttribute('aria-invalid', 'true');
    if (message) { message.textContent = error.message; message.hidden = false; }
    input.focus();
  } else {
    notice(error.message, true);
    $('notice').focus();
  }
}
function clearErrors() {
  document.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute('aria-invalid'));
  document.querySelectorAll('.field-error').forEach(error => { error.hidden = true; error.textContent = ''; });
}
function safe(fn) {
  let busy = false;
  return async event => {
    event?.preventDefault();
    if (busy) return;
    busy = true;
    const trigger = event?.submitter || (event?.currentTarget?.tagName === 'BUTTON' ? event.currentTarget : null);
    if (trigger) trigger.setAttribute('aria-disabled', 'true');
    try { notice(''); clearErrors(); await fn(event); }
    catch (error) { showError(error); }
    finally { if (trigger?.isConnected) { if (trigger.id === 'run-agent' && reviewRunning) trigger.setAttribute('aria-disabled', 'true'); else trigger.removeAttribute('aria-disabled'); } busy = false; }
  };
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {}), ...options.headers}});
  if (!response.ok) {
    let data;
    try { data = await response.json(); } catch { data = {}; }
    throw new Error(data.error?.message || `Request failed (${response.status})`);
  }
  return response.json();
}
async function session() {
  if (!token) {
    const data = await api('/api/sessions', {method: 'POST', body: '{}'});
    token = data.token;
    sessionStorage.setItem('modelcheck-token', token);
  }
}
function pct(value) { return value === null || value === undefined ? '—' : `${(100 * value).toFixed(1)}%`; }
function badge(id, text, kind) { $(id).textContent = text; $(id).className = `badge ${kind}`; }
async function health() {
  const data = await api('/healthz');
  live = data.api_key_configured;
  $('run-agent').disabled = !bundleId || !live;
  $('run-agent').setAttribute('aria-disabled', String(reviewRunning));
  $('provider-status').textContent = live ? `Live review ready · ${data.model}` : 'Live review needs an OpenRouter key in .env. Data inspection and recorded review are available.';
}
function describe() {
  const sample = samples.find(item => item.id === $('scenario').value);
  $('scenario-description').textContent = sample?.description || '';
}
function cancelPolling() {
  clearTimeout(pollTimer);
  reviewRunning = false;
  $('run-agent').removeAttribute('aria-busy');
}
function primaryAction(pending) {
  $('run-agent').classList.toggle('primary', !pending);
  $('run-agent').classList.toggle('secondary', pending);
}
async function load(data) {
  await session();
  cancelPolling();
  const loaded = await api('/api/bundles', {method: 'POST', body: JSON.stringify(data)});
  bundleId = loaded.bundle_id;
  $('dataset-caption').textContent = `${loaded.validation.test_samples} test examples · ${loaded.validation.sources.length} sources · ${loaded.validation.runs.length} runs${loaded.validation.synthetic ? ' · synthetic' : ''}`;
  badge('validation-badge', loaded.validation.status === 'ready' ? 'Data loaded' : 'Needs attention', loaded.validation.status === 'ready' ? 'good' : 'danger');
  const findings = $('validation-findings');
  findings.replaceChildren();
  if (loaded.validation.findings.length) {
    const list = node('div', undefined, 'validation-list');
    loaded.validation.findings.forEach(finding => list.append(node('div', `${finding.severity === 'error' ? 'Error' : 'Warning'}: ${finding.message}`, `validation-item ${finding.severity === 'error' ? 'error' : ''}`)));
    findings.append(list);
  }
  const result = await api('/api/inspections', {method: 'POST', body: JSON.stringify({bundle_id: bundleId, question: 'Inspect the data.'})});
  renderReview(result);
  await health();
  announce(`Inspection complete. ${loaded.validation.test_samples} test examples. ${loaded.validation.findings.length} validation ${loaded.validation.findings.length === 1 ? 'finding' : 'findings'}.`);
}
function renderMetrics(evidence) {
  const root = $('metric-cards');
  root.replaceChildren();
  const comparison = evidence.find(item => item.tool === 'compare_runs')?.result;
  const runs = evidence.filter(item => item.tool === 'compute_metrics').map(item => item.result);
  if (!runs.length && !comparison) {
    root.append(node('p', 'Metric evidence is unavailable for this review. Inspect the data or resolve validation errors.', 'help'));
    $('source-table').replaceChildren();
    return;
  }
  const baseline = comparison?.baseline || runs.find(run => run.source === null) || runs[0], candidate = comparison?.candidate;
  for (const [label, key] of [['Accuracy', 'accuracy'], ['Positive recall', 'recall'], ['F1 score', 'f1']]) {
    const card = node('div', undefined, 'metric-card');
    card.append(node('div', label, 'metric-title'), node('div', pct(candidate ? candidate[key] : baseline[key]), 'metric-value'), node('div', candidate ? `Candidate · baseline ${pct(baseline[key])}` : `${baseline.run_id}${baseline.source ? ' · ' + baseline.source : ''} · n = ${baseline.n}/${baseline.total}`, 'metric-sub'));
    if (candidate) {
      const delta = candidate[key] === null || baseline[key] === null ? null : 100 * (candidate[key] - baseline[key]);
      card.append(node('div', delta === null ? 'Undefined denominator' : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toFixed(1)} pp`, 'metric-change' + (delta < 0 ? ' negative' : '')));
    }
    root.append(card);
  }
  const area = $('source-table');
  area.replaceChildren();
  if (comparison) {
    area.append(node('h3', 'Results by source', 'section-caption'));
    const hint = node('p', 'Scroll the table horizontally to see all columns.', 'help table-hint');
    hint.id = 'source-table-hint';
    const wrap = node('div', undefined, 'table-scroll');
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Results by source table');
    wrap.setAttribute('aria-describedby', hint.id);
    const table = node('table'), head = node('tr');
    const caption = node('caption', 'Recall and false negatives on matched test examples', 'sr-only');
    ['Source', 'Examples', 'Baseline recall', 'Candidate recall', 'Candidate FN'].forEach(text => { const cell = node('th', text); cell.scope = 'col'; head.append(cell); });
    const thead = node('thead');
    thead.append(head);
    table.append(caption, thead);
    const body = node('tbody');
    comparison.slices.forEach(slice => {
      const row = node('tr'), source = node('th', slice.source);
      source.scope = 'row';
      row.append(source);
      [slice.n, pct(slice.baseline.recall), pct(slice.candidate.recall), slice.candidate.counts.fn].forEach(value => row.append(node('td', String(value))));
      body.append(row);
    });
    table.append(body);
    wrap.append(table);
    area.append(hint, wrap, node('p', 'FN = false negatives. Both runs cover the same complete test population. Source differences do not establish causality.', 'legend'));
    if (comparison.slices_truncated) area.append(node('p', `Showing ${comparison.slices.length} of ${comparison.source_count} sources. Ask for metrics on a named source to inspect the others.`, 'validation-item'));
  } else {
    area.append(node('p', runs.map(run => `${run.run_id}: ${run.n}/${run.total} examples · ${run.population}`).join(' | '), 'legend'));
  }
}
function renderReview(data) {
  review = data;
  const inProgress = ['running', 'queued'].includes(data.status);
  if (!inProgress || (data.evidence || []).some(item => ['compute_metrics', 'compare_runs'].includes(item.tool))) renderMetrics(data.evidence || []);
  const area = $('review-content');
  area.replaceChildren();
  area.className = '';
  area.setAttribute('aria-busy', String(inProgress));
  if (data.status === 'failed') {
    badge('review-mode', 'Review failed', 'danger');
    area.append(node('p', data.error?.message || 'Review failed.', 'help'));
  } else if (inProgress) {
    badge('review-mode', data.status === 'queued' ? 'Queued' : 'Investigating', 'warning');
    area.append(node('p', 'The agent is investigating. Completed tool events appear in Activity & evidence.', 'help'));
  } else {
    const report = data.report || {};
    badge('review-mode', data.mode === 'deterministic' ? 'Tools only · no LLM' : data.mode === 'recorded' ? 'Recorded AI review' : 'Live AI review', data.mode === 'deterministic' ? 'neutral' : 'good');
    area.append(node('p', report.summary || 'Inspection complete.', 'review-summary'));
    for (const finding of report.findings || []) {
      const element = node('div', finding.statement, 'finding');
      const refs = node('small', (finding.evidence_ids || []).join(' · '));
      refs.dir = 'auto';
      element.append(refs);
      area.append(element);
    }
    if (report.limitations?.length) area.append(node('div', report.limitations.join(' '), 'limitations'));
    if (data.application_notice) area.append(node('div', data.application_notice, 'validation-item'));
  }
  $('review-caption').textContent = data.mode === 'deterministic' ? 'Calculated through the local MCP server.' : 'Measured tools, cited evidence, bounded model calls.';
  const done = data.status === 'completed';
  ['draft-proposal', 'export-json', 'export-md'].forEach(id => { $(id).disabled = !done; });
  const log = $('trace-log');
  log.replaceChildren();
  (data.events || []).forEach(event => log.append(node('div', `${event.kind.replaceAll('_', ' ')}${event.tool ? ' · ' + event.tool : ''}${event.model ? ' · ' + event.model : ''}${event.error ? ' · ' + (event.error.message || event.error.code) : ''}`, 'trace-event')));
  $('trace-count').textContent = `${data.events?.length || 0} events`;
  const receipt = $('evidence-receipt');
  receipt.replaceChildren();
  (data.evidence || []).forEach(evidence => {
    const details = node('details', undefined, 'evidence-item');
    details.append(node('summary', `${evidence.tool} · ${evidence.evidence_id}`), node('pre', JSON.stringify(evidence.result, null, 2)));
    receipt.append(details);
  });
  if (data.pending_action) renderAction(data.pending_action);
  else { $('proposal-section').hidden = true; renderedAction = ''; primaryAction(false); }
}
async function runAgent() {
  if (!bundleId || reviewRunning) return;
  const question = $('question').value.trim();
  if (!question) throw fieldError('question', 'Enter an investigation question.');
  reviewRunning = true;
  $('run-agent').setAttribute('aria-disabled', 'true');
  $('run-agent').setAttribute('aria-busy', 'true');
  const expected = bundleId;
  try {
    const queued = await api('/api/reviews', {method: 'POST', body: JSON.stringify({bundle_id: bundleId, question, config: 'B'})});
    announce('Review queued. The agent will investigate the loaded experiment.');
    async function poll() {
      try {
        const data = await api(`/api/reviews/${queued.id}`);
        if (bundleId !== expected) return;
        renderReview(data);
        if (['completed', 'failed'].includes(data.status)) {
          cancelPolling();
          await health();
          if (data.status === 'failed') notice(data.error?.message || 'Review failed.', true);
          else announce(`AI review complete. ${data.report?.findings?.length || 0} findings. Review the evidence before preparing a follow-up.`);
          return;
        }
        pollTimer = setTimeout(poll, 1000);
      } catch (error) { cancelPolling(); showError(error); await health(); }
    }
    await poll();
  } catch (error) { cancelPolling(); await health(); throw error; }
}
function renderAction(action, focus = false) {
  const key = `${action.id}:${action.status}:${action.digest}`;
  if (renderedAction === key) return;
  renderedAction = key;
  $('proposal-section').hidden = false;
  $('proposal-form').hidden = true;
  primaryAction(action.status === 'pending');
  const area = $('proposal-content');
  area.replaceChildren();
  const list = node('dl');
  for (const property of ['objective', 'change', 'selection_rule', 'success_criterion', 'held_out_test']) {
    const row = node('div', undefined, 'proposal-row');
    row.append(node('dt', {objective: 'Objective', change: 'Change', selection_rule: 'Selection rule', success_criterion: 'Success criterion', held_out_test: 'Held-out test'}[property]), node('dd', action.spec[property]));
    list.append(row);
  }
  area.append(list);
  if (action.status === 'pending') {
    area.append(node('p', `Exact proposal · ${action.digest}`, 'digest'));
    const buttons = node('div', undefined, 'approval-actions');
    for (const [text, approved] of [['Approve & save', true], ['Reject', false]]) {
      const button = node('button', text, approved ? 'button primary' : 'text-button');
      button.type = 'button';
      button.dataset.static = '';
      button.addEventListener('click', safe(async () => {
        const result = await api(`/api/actions/${action.id}/decision`, {method: 'POST', body: JSON.stringify({approved, digest: action.digest})});
        if (review) review.pending_action = result;
        renderAction(result, true);
        announce(approved ? 'Specification saved. The experiment JSON is ready to download.' : 'Proposal rejected. No specification was saved.');
      }));
      buttons.append(button);
    }
    area.append(buttons);
    if (focus) $('proposal-heading').focus();
  } else {
    const result = node('p', action.status === 'saved' ? `Saved exactly once · ${action.filename}` : 'Proposal rejected. No experiment specification was saved.', 'saved-banner');
    result.tabIndex = -1;
    area.append(result);
    if (action.status === 'saved') {
      const button = node('button', 'Download experiment JSON ↓', 'text-button');
      button.type = 'button';
      button.addEventListener('click', safe(() => download(`/api/actions/${action.id}/download`, action.filename)));
      area.append(button);
    }
    if (focus) result.focus();
  }
}
async function download(url, name) {
  const response = await fetch(url, {headers: {Authorization: `Bearer ${token}`}});
  if (!response.ok) throw new Error('Download unavailable.');
  const blob = await response.blob(), link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  announce(`${name} download started.`);
}
async function readFile(id, required) {
  const file = $(id).files[0];
  if (!file) { if (required) throw fieldError(id, 'Choose this required CSV file.'); return null; }
  if (file.size > 1024 * 1024) throw fieldError(id, `${file.name} exceeds 1 MiB.`);
  return file.text();
}
function switchTab(index, focus = false) {
  const tabs = [$('sample-tab'), $('upload-tab')], panels = [$('sample-pane'), $('upload-pane')];
  tabs.forEach((tab, i) => { tab.setAttribute('aria-selected', String(i === index)); tab.tabIndex = i === index ? 0 : -1; panels[i].hidden = i !== index; });
  if (focus) tabs[index].focus();
}
[$('sample-tab'), $('upload-tab')].forEach((tab, index) => {
  tab.onclick = () => switchTab(index);
  tab.onkeydown = event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    switchTab(event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index, true);
  };
});
$('scenario').onchange = describe;
$('load-sample').onclick = safe(() => load({sample_id: $('scenario').value}));
$('upload-form').onsubmit = safe(async () => {
  const manifest_csv = await readFile('manifest-file', true), baseline = await readFile('baseline-file', true), candidate = await readFile('candidate-file', false), meta = await readFile('metadata-file', false);
  let metadata = {};
  if (meta) {
    try { metadata = JSON.parse(meta); } catch { throw fieldError('metadata-file', 'Metadata must be valid JSON.'); }
    if (metadata === null || Array.isArray(metadata) || typeof metadata !== 'object') throw fieldError('metadata-file', 'Metadata must be a JSON object with optional run information.');
  }
  try { await load({manifest_csv, predictions: candidate ? [baseline, candidate] : [baseline], metadata}); }
  catch (error) {
    const message = error.message.toLowerCase();
    const field = message.startsWith('manifest:') ? 'manifest-file' : message.startsWith('predictions 1:') ? 'baseline-file' : message.startsWith('predictions 2:') ? 'candidate-file' : message.includes('metadata') ? 'metadata-file' : null;
    if (field) throw fieldError(field, error.message);
    throw error;
  }
});
$('download-sample').onclick = safe(async () => {
  const data = await api(`/api/samples/${$('scenario').value}/files`);
  const files = [['manifest.csv', data.manifest_csv], ['baseline.csv', data.predictions[0]], ['candidate.csv', data.predictions[1]], ['metadata.json', JSON.stringify(data.metadata, null, 2)]];
  for (const [name, text] of files) {
    if (text === undefined) continue;
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([text], {type: 'text/plain'}));
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
  announce('Example file downloads started.');
});
$('review-form').onsubmit = safe(runAgent);
document.querySelectorAll('[data-prompt]').forEach(button => { button.onclick = () => { $('question').value = button.dataset.prompt; $('question').focus(); clearErrors(); }; });
$('draft-proposal').onclick = () => {
  $('proposal-section').hidden = false;
  $('proposal-form').hidden = false;
  $('proposal-content').replaceChildren();
  renderedAction = '';
  primaryAction(false);
  $('objective').focus();
};
$('proposal-form').onsubmit = safe(async () => {
  for (const [id, label] of [['objective', 'objective'], ['change', 'proposed change'], ['criterion', 'success criterion']]) {
    if ($(id).value.trim().length < 5) throw fieldError(id, `Enter at least five characters for the ${label}.`);
  }
  const ids = (review.evidence || []).filter(item => item.tool !== 'load_review_protocol').map(item => item.evidence_id);
  if (!ids.length) throw new Error('Inspect data before creating a specification.');
  const spec = {objective: $('objective').value.trim(), change: $('change').value.trim(), selection_rule: 'Select the change using validation data only; never tune on the held-out test set.', success_criterion: $('criterion').value.trim(), run_ids: ['run-1'], evidence_ids: ids.slice(0, 5)};
  const action = await api('/api/proposals', {method: 'POST', body: JSON.stringify({review_id: review.id, spec})});
  review.pending_action = action;
  renderAction(action, true);
  announce('Exact specification ready. Review it, then approve or reject.');
});
$('export-json').onclick = safe(() => download(`/api/reviews/${review.id}/export?format=json`, 'modelcheck-review.json'));
$('export-md').onclick = safe(() => download(`/api/reviews/${review.id}/export?format=markdown`, 'modelcheck-review.md'));
$('reset').onclick = safe(async () => {
  cancelPolling();
  if (token) await api('/api/sessions/current', {method: 'DELETE', body: '{}'});
  token = null;
  sessionStorage.removeItem('modelcheck-token');
  bundleId = null;
  review = null;
  await session();
  await load({sample_id: $('scenario').value});
  notice('Session reset. Previous uploads, pending approvals and generated specifications were removed.');
});
$('replay-review').onclick = safe(async () => {
  await session();
  cancelPolling();
  const data = await api('/api/replays/comparison', {method: 'POST', body: '{}'});
  bundleId = data.bundle_id;
  $('scenario').value = 'comparison';
  describe();
  $('dataset-caption').textContent = '40 test examples · 2 sources · 2 runs · synthetic recorded scenario';
  badge('validation-badge', 'Recorded sample', 'neutral');
  $('validation-findings').replaceChildren();
  renderReview(data);
  await health();
  announce('Recorded AI review loaded. This is a replay; no model request was sent.');
});
document.querySelectorAll('input,textarea').forEach(input => {
  input.addEventListener(input.type === 'file' ? 'change' : 'input', () => {
    input.removeAttribute('aria-invalid');
    const error = $(input.id + '-error');
    if (error) error.hidden = true;
  });
});
safe(async () => {
  await session();
  samples = await api('/api/samples');
  samples.forEach(sample => { const option = node('option', sample.name); option.value = sample.id; $('scenario').append(option); });
  describe();
  await load({sample_id: 'comparison'});
  setInterval(() => health().catch(() => {}), 15000);
})();
