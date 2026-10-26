/**
 * NexusAI Frontend — Multi-Agent Orchestration Dashboard
 * Handles SSE streaming, workflow submission, and real-time UI updates.
 */

const API_BASE = '/api/v1';
let currentSessionId = null;
let eventSource = null;
let isProcessing = false;

// ── Agent metadata ──────────────────────────────────────────────
const AGENT_META = {
  planner:    { icon: '🧠', label: 'Planner',   color: '#6366f1' },
  retriever:  { icon: '🔍', label: 'Retriever', color: '#06b6d4' },
  analyzer:   { icon: '📊', label: 'Analyzer',  color: '#f59e0b' },
  writer:     { icon: '✍️',  label: 'Writer',    color: '#10b981' },
  critic:     { icon: '🎯', label: 'Critic',    color: '#ec4899' },
  orchestrator:{ icon: '🤖', label: 'System',   color: '#8b5cf6' },
};

// ── DOM helpers ─────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

function getApiKey() {
  return $('apiKeyInput').value.trim() || 'dev-key-12345';
}

function authHeaders() {
  return { 'Content-Type': 'application/json', 'X-API-Key': getApiKey() };
}

// ── Tab switching ────────────────────────────────────────────────
function switchTab(tab) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  $(`tab${tab.charAt(0).toUpperCase() + tab.slice(1)}`).classList.add('active');
  $(`nav${tab.charAt(0).toUpperCase() + tab.slice(1)}`).classList.add('active');
  if (tab === 'sessions') loadSessions();
}

// ── Health check ─────────────────────────────────────────────────
async function checkHealth() {
  const dot = document.querySelector('.status-dot');
  const text = $('statusText');
  try {
    const res = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    if (data.redis === 'connected') {
      dot.className = 'status-dot online';
      text.textContent = 'Redis Online';
    } else {
      dot.className = 'status-dot offline';
      text.textContent = 'Redis Offline';
    }
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = 'API Offline';
  }
}

// ── Query submission ─────────────────────────────────────────────
async function sendQuery() {
  const input = $('queryInput');
  const query = input.value.trim();
  if (!query || isProcessing) return;

  const priority = $('prioritySelect').value;

  // Show chat, hide welcome
  $('welcomeScreen').style.display = 'none';
  $('chatMessages').style.display = 'flex';
  $('pipelinePanel').style.display = 'block';

  appendUserMessage(query);
  input.value = '';
  input.style.height = 'auto';

  setProcessing(true);
  const thinkingId = appendThinkingBubble();

  try {
    const res = await fetch(`${API_BASE}/workflow`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ query, priority }),
    });

    if (!res.ok) {
      const err = await res.json();
      removeThinkingBubble(thinkingId);
      appendSystemMessage(`❌ Error: ${err.error || 'Request failed'}`, 'error');
      setProcessing(false);
      return;
    }

    const data = await res.json();
    currentSessionId = data.session_id;

    removeThinkingBubble(thinkingId);
    resetPipeline();
    streamWorkflow(currentSessionId);

  } catch (err) {
    removeThinkingBubble(thinkingId);
    appendSystemMessage(`❌ Network error: ${err.message}`, 'error');
    setProcessing(false);
  }
}

// ── SSE Streaming ────────────────────────────────────────────────
function streamWorkflow(sessionId) {
  if (eventSource) eventSource.close();

  const url = `${API_BASE}/workflow/${sessionId}/stream`;
  eventSource = new EventSource(url + `?api_key=${encodeURIComponent(getApiKey())}`);

  eventSource.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data);
      handleStreamEvent(payload);
    } catch (err) {
      console.error('Stream parse error:', err);
    }
  };

  eventSource.onerror = () => {
    // SSE will reconnect automatically; just update status
    updateStatusPill('working', 'Reconnecting…');
  };
}

function handleStreamEvent(payload) {
  switch (payload.type) {
    case 'status':
      handleStatusChange(payload.status);
      break;

    case 'agent_message':
      showAgentToast(payload);
      updatePipelineStep(payload.agent, 'active');
      break;

    case 'plan_progress':
      updatePipelineFromPlan(payload.subtasks);
      break;

    case 'done':
      handleDone(payload);
      break;

    case 'stream_closed':
    case 'error':
      setProcessing(false);
      if (payload.error) appendSystemMessage(`❌ ${payload.error}`, 'error');
      break;
  }
}

function handleStatusChange(status) {
  const dot = document.querySelector('.status-dot');
  const text = $('statusText');
  const statusMap = {
    pending:      ['working', 'Planning…'],
    in_progress:  ['working', 'Working…'],
    completed:    ['online',  'Completed'],
    failed:       ['offline', 'Failed'],
  };
  const [cls, label] = statusMap[status] || ['working', status];
  dot.className = `status-dot ${cls}`;
  text.textContent = label;
}

function handleDone(payload) {
  if (eventSource) { eventSource.close(); eventSource = null; }
  setProcessing(false);

  if (payload.result) {
    appendAgentMessage('writer', payload.result, true);
  } else if (payload.error) {
    appendSystemMessage(`❌ Workflow failed: ${payload.error}`, 'error');
  }

  // Mark all steps as done
  document.querySelectorAll('.pipeline-step').forEach(el => {
    if (!el.classList.contains('failed')) el.className = 'pipeline-step done';
  });
  $('progressBar').style.width = '100%';

  checkHealth();
}

// ── Pipeline visualization ────────────────────────────────────────
const PIPELINE_ORDER = ['planner', 'retriever', 'analyzer', 'writer', 'critic'];

function resetPipeline() {
  const steps = $('pipelineSteps');
  steps.innerHTML = PIPELINE_ORDER.map(role => {
    const meta = AGENT_META[role];
    return `<div class="pipeline-step" id="step-${role}">
      <span class="step-icon">${meta.icon}</span>
      <span>${meta.label}</span>
    </div>`;
  }).join('');
  $('progressBar').style.width = '0%';
}

function updatePipelineStep(agentRole, state) {
  const step = $(`step-${agentRole}`);
  if (!step) return;
  step.className = `pipeline-step ${state}`;

  // Update progress bar
  const idx = PIPELINE_ORDER.indexOf(agentRole);
  if (idx >= 0) {
    const pct = Math.round(((idx + 1) / PIPELINE_ORDER.length) * 100);
    $('progressBar').style.width = `${pct}%`;
  }
}

function updatePipelineFromPlan(subtasks) {
  if (!subtasks || !subtasks.length) return;
  subtasks.forEach(task => {
    const step = $(`step-${task.agent}`);
    if (!step) return;
    const stateMap = {
      completed: 'done',
      in_progress: 'active',
      failed: 'failed',
      pending: '',
    };
    const cls = stateMap[task.status] || '';
    if (cls) step.className = `pipeline-step ${cls}`;
  });
}

// ── Message rendering ─────────────────────────────────────────────
function appendUserMessage(text) {
  const container = $('chatMessages');
  const div = document.createElement('div');
  div.className = 'message user';
  div.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-body">
      <div class="message-meta">You · ${timeNow()}</div>
      <div class="message-bubble">${escapeHtml(text)}</div>
    </div>`;
  container.appendChild(div);
  scrollToBottom();
}

function appendAgentMessage(role, content, withActions = false) {
  const container = $('chatMessages');
  const meta = AGENT_META[role] || AGENT_META.orchestrator;
  const div = document.createElement('div');
  div.className = 'message';

  const actionsHtml = withActions ? `
    <div class="result-actions">
      <button class="action-btn" onclick="copyToClipboard(this)">📋 Copy</button>
      <button class="action-btn" onclick="downloadReport(this)">⬇️ Download</button>
    </div>` : '';

  div.innerHTML = `
    <div class="message-avatar">${meta.icon}</div>
    <div class="message-body">
      <div class="message-meta" style="color:${meta.color}">${meta.label} Agent · ${timeNow()}</div>
      <div class="message-bubble">${markdownToHtml(content)}</div>
      ${actionsHtml}
    </div>`;
  container.appendChild(div);
  scrollToBottom();
}

function appendSystemMessage(text, type = 'info') {
  const container = $('chatMessages');
  const colors = { info: '#6366f1', error: '#ef4444', success: '#10b981' };
  const div = document.createElement('div');
  div.className = 'message';
  div.innerHTML = `
    <div class="message-avatar">⚙️</div>
    <div class="message-body">
      <div class="message-meta" style="color:${colors[type] || colors.info}">System · ${timeNow()}</div>
      <div class="message-bubble">${escapeHtml(text)}</div>
    </div>`;
  container.appendChild(div);
  scrollToBottom();
}

function appendThinkingBubble() {
  const container = $('chatMessages');
  const id = 'thinking-' + Date.now();
  const div = document.createElement('div');
  div.className = 'message';
  div.id = id;
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-body">
      <div class="message-meta">NexusAI · Thinking…</div>
      <div class="thinking-bubble">
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
        <div class="thinking-dot"></div>
        <span style="font-size:12px;color:var(--text-muted);margin-left:4px">Agents are working…</span>
      </div>
    </div>`;
  container.appendChild(div);
  scrollToBottom();
  return id;
}

function removeThinkingBubble(id) {
  const el = $(id);
  if (el) el.remove();
}

// ── Toast notifications ───────────────────────────────────────────
function showAgentToast(payload) {
  const meta = AGENT_META[payload.agent] || AGENT_META.orchestrator;
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'toast agent-msg';
  toast.innerHTML = `${meta.icon} <strong style="color:${meta.color}">${meta.label}</strong>: ${escapeHtml(payload.preview?.substring(0, 80) || 'Working…')}`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ── Sessions list ─────────────────────────────────────────────────
async function loadSessions() {
  const grid = $('sessionsGrid');
  grid.innerHTML = '<div class="empty-state">Loading…</div>';
  try {
    const res = await fetch(`${API_BASE}/sessions`, { headers: authHeaders() });
    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();

    if (!data.sessions || data.sessions.length === 0) {
      grid.innerHTML = '<div class="empty-state">No active sessions. Start a workflow to see it here.</div>';
      return;
    }

    grid.innerHTML = data.sessions.map(s => `
      <div class="session-card" onclick="viewSession('${s.session_id}')">
        <div class="session-status ${s.status}">
          ${statusEmoji(s.status)} ${s.status.replace('_', ' ')}
        </div>
        <div class="session-query">${escapeHtml(s.query)}</div>
        <div class="session-meta">${s.session_id.substring(0,8)}… · ${formatDate(s.created_at)}</div>
      </div>
    `).join('');
  } catch (err) {
    grid.innerHTML = `<div class="empty-state">Failed to load sessions: ${err.message}</div>`;
  }
}

async function viewSession(sessionId) {
  switchTab('chat');
  $('welcomeScreen').style.display = 'none';
  $('chatMessages').style.display = 'flex';

  try {
    const res = await fetch(`${API_BASE}/workflow/${sessionId}/status`, { headers: authHeaders() });
    const data = await res.json();

    appendSystemMessage(`📂 Loaded session ${sessionId.substring(0,8)}… (${data.status})`);
    if (data.result) appendAgentMessage('writer', data.result, true);
  } catch (err) {
    appendSystemMessage(`❌ Could not load session: ${err.message}`, 'error');
  }
}

// ── Utility functions ─────────────────────────────────────────────
function setProcessing(val) {
  isProcessing = val;
  const btn = $('sendBtn');
  btn.disabled = val;
}

function updateStatusPill(state, text) {
  document.querySelector('.status-dot').className = `status-dot ${state}`;
  $('statusText').textContent = text;
}

function fillQuery(text) {
  $('queryInput').value = text;
  $('queryInput').focus();
  autoResizeTextarea();
}

function scrollToBottom() {
  const area = $('messagesArea');
  requestAnimationFrame(() => { area.scrollTop = area.scrollHeight; });
}

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(iso) {
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function statusEmoji(status) {
  return { completed: '✅', in_progress: '⚡', failed: '❌', pending: '⏳' }[status] || '•';
}

// ── Minimal Markdown → HTML converter ────────────────────────────
function markdownToHtml(md) {
  if (!md) return '';
  return md
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^#{3}\s+(.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{2}\s+(.+)$/gm, '<h2>$1</h2>')
    .replace(/^#{1}\s+(.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    .replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^(.+)$/, '<p>$1</p>');
}

// ── Copy / Download ───────────────────────────────────────────────
function copyToClipboard(btn) {
  const bubble = btn.closest('.message-body').querySelector('.message-bubble');
  navigator.clipboard.writeText(bubble.innerText).then(() => {
    btn.textContent = '✅ Copied!';
    setTimeout(() => btn.textContent = '📋 Copy', 2000);
  });
}

function downloadReport(btn) {
  const bubble = btn.closest('.message-body').querySelector('.message-bubble');
  const text = bubble.innerText;
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `nexusai-report-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Textarea auto-resize & keyboard shortcuts ─────────────────────
function autoResizeTextarea() {
  const ta = $('queryInput');
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  const input = $('queryInput');
  input.addEventListener('input', autoResizeTextarea);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  });

  // Health check on load and every 30 seconds
  checkHealth();
  setInterval(checkHealth, 30000);

  // SSE requires the API key in query string since EventSource doesn't support headers
  // We patch EventSource URL above to include api_key query param
});
