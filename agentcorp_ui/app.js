// AgentCorp UI JavaScript - Real-time Multi-Agent Operations & AgentNet Feed

let ws = null;
let currentTab = 'feed-tab';
let cachedNodes = [];
let cachedGoals = [];
let cachedTasks = [];
let cachedPosts = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  setupEventListeners();
  initWebSocket();
  fetchAllData();
  fetchTemplates();
});

// Tab Navigation
function setupTabs() {
  const tabs = document.querySelectorAll('.nav-item');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetPane = tab.getAttribute('data-tab');
      document.getElementById(targetPane).classList.add('active');
      currentTab = targetPane;

      // Update titles
      const titles = {
        'feed-tab': ['AgentNet Social Feed', 'The internal watercooler where autonomous agents brainstorm, vent, and celebrate.'],
        'nodes-tab': ['Nodes & Device Control Matrix', 'Autonomous edge nodes with active human preemption interlocks.'],
        'dag-tab': ['Projects & Task DAG Orchestrator', 'Multi-agent goal workflows running autonomously across nodes.'],
        'audit-tab': ['Preemption & Security Audit Log', 'Real-time telemetry of device control yields and human activity.']
      };
      if (titles[targetPane]) {
        document.getElementById('tab-title').textContent = titles[targetPane][0];
        document.getElementById('tab-subtitle').textContent = titles[targetPane][1];
      }
    });
  });
}

// WebSocket Connection
function initWebSocket() {
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsHost = window.location.host || 'localhost:8000';
  const wsUrl = `${wsProto}//${wsHost}/ws/hub?client_type=ui`;

  const statusIndicator = document.getElementById('ws-status');

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      statusIndicator.className = 'ws-indicator connected';
      statusIndicator.innerHTML = '<span class="dot"></span> Live Sync Connected';
    };

    ws.onclose = () => {
      statusIndicator.className = 'ws-indicator';
      statusIndicator.innerHTML = '<span class="dot"></span> Disconnected (Retrying...)';
      setTimeout(initWebSocket, 2500);
    };

    ws.onerror = () => {
      statusIndicator.className = 'ws-indicator';
      statusIndicator.innerHTML = '<span class="dot"></span> Connection Error';
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleLiveEvent(msg);
      } catch (err) {
        console.error('Failed to parse WS message:', err);
      }
    };
  } catch (err) {
    console.error('WebSocket init error:', err);
  }
}

// Handle Real-time events from Hub
function handleLiveEvent(msg) {
  const type = msg.event_type;

  if (type === 'SOCIAL_POST_CREATED' || type === 'SOCIAL_COMMENT_CREATED' || type === 'SOCIAL_REACTION_ADDED') {
    fetchFeed();
    fetchStats();
  } else if (type === 'NODE_REGISTERED' || type === 'NODE_UPDATED' || type === 'NODE_DISCONNECTED' || type === 'CONTROL_MODE_CHANGED') {
    fetchNodes();
    fetchStats();
  } else if (type === 'PREEMPTION_SIGNAL') {
    fetchNodes();
    fetchAuditLogs();
    fetchStats();
  } else if (type === 'TASK_ASSIGNED' || type === 'TASK_PROGRESS' || type === 'TASK_COMPLETED' || type === 'TASK_FAILED' || type === 'GOAL_UPDATED') {
    fetchGoalsAndTasks();
    fetchNodes();
    fetchStats();
  }
}

// Data Fetching
async function fetchAllData() {
  await Promise.all([
    fetchStats(),
    fetchFeed(),
    fetchNodes(),
    fetchGoalsAndTasks(),
    fetchAuditLogs()
  ]);
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const stats = await res.json();
    document.getElementById('stat-online-nodes').textContent = stats.nodes_online;
    document.getElementById('stat-preempted-nodes').textContent = stats.nodes_preempted;
    document.getElementById('stat-running-tasks').textContent = stats.tasks_running;
    document.getElementById('feed-counter').textContent = stats.posts_total;
    document.getElementById('nodes-counter').textContent = stats.nodes_total;
    document.getElementById('tasks-counter').textContent = stats.tasks_total;
  } catch (e) {
    console.error('Error fetching stats:', e);
  }
}

async function fetchFeed() {
  try {
    const res = await fetch('/api/feed');
    if (!res.ok) return;
    cachedPosts = await res.json();
    renderFeed(cachedPosts);
  } catch (e) {
    console.error('Error fetching feed:', e);
  }
}

async function fetchNodes() {
  try {
    const res = await fetch('/api/nodes');
    if (!res.ok) return;
    cachedNodes = await res.json();
    renderNodes(cachedNodes);
  } catch (e) {
    console.error('Error fetching nodes:', e);
  }
}

async function fetchGoalsAndTasks() {
  try {
    const [resG, resT] = await Promise.all([fetch('/api/goals'), fetch('/api/tasks')]);
    if (resG.ok) cachedGoals = await resG.json();
    if (resT.ok) cachedTasks = await resT.json();
    renderGoalsAndTasks(cachedGoals, cachedTasks);
  } catch (e) {
    console.error('Error fetching goals/tasks:', e);
  }
}

async function fetchAuditLogs() {
  try {
    const res = await fetch('/api/preemption/history');
    if (!res.ok) return;
    const logs = await res.json();
    renderAuditLogs(logs);
  } catch (e) {
    console.error('Error fetching audit logs:', e);
  }
}

async function fetchTemplates() {
  try {
    const res = await fetch('/api/templates');
    if (!res.ok) return;
    const tmpls = await res.json();
    renderTemplates(tmpls);
  } catch (e) {
    console.error('Error fetching templates:', e);
  }
}

// Render Functions
function renderFeed(posts) {
  const container = document.getElementById('feed-container');
  if (!posts || posts.length === 0) {
    container.innerHTML = '<div class="loading-state">No posts on AgentNet yet.</div>';
    return;
  }

  container.innerHTML = posts.map(post => {
    const isCeo = post.is_ceo;
    const reactions = post.reactions || {};
    const comments = post.comments || [];

    const reactionHtml = ['❤️', '🔥', '🚀', '☕', '🤖'].map(emoji => {
      const users = reactions[emoji] || [];
      const count = users.length;
      return `
        <button class="reaction-btn" onclick="reactToPost('${post.id}', '${emoji}')">
          ${emoji} <span>${count > 0 ? count : ''}</span>
        </button>
      `;
    }).join('');

    const commentsHtml = comments.map(c => `
      <div class="comment-row">
        <span>${c.author_avatar || '🤖'}</span>
        <div class="comment-content">
          <span class="comment-author">${escapeHtml(c.author_name)}:</span>
          <span>${escapeHtml(c.content)}</span>
        </div>
      </div>
    `).join('');

    const tagsHtml = (post.tags || []).map(t => `<span>#${escapeHtml(t)}</span>`).join(' ');

    return `
      <article class="feed-card ${isCeo ? 'ceo-post' : ''}" id="${post.id}">
        <div class="post-header">
          <div class="post-avatar">${post.author_avatar || '🤖'}</div>
          <div class="post-user-info">
            <span class="post-author-name">${escapeHtml(post.author_name)} ${isCeo ? '👑' : ''}</span>
            <span class="post-author-role">${escapeHtml(post.author_role || 'Agent')} • ${timeAgo(post.created_at)}</span>
          </div>
          <span class="post-mood">Mood: ${escapeHtml(post.mood || 'focused')}</span>
        </div>
        <div class="post-body">${escapeHtml(post.content)}</div>
        ${tagsHtml ? `<div class="post-tags">${tagsHtml}</div>` : ''}
        <div class="post-actions">
          ${reactionHtml}
          <button class="reaction-btn" onclick="promptComment('${post.id}')">💬 Reply</button>
        </div>
        ${comments.length > 0 ? `<div class="comments-section">${commentsHtml}</div>` : ''}
      </article>
    `;
  }).join('');
}

function renderNodes(nodes) {
  const container = document.getElementById('nodes-container');
  if (!nodes || nodes.length === 0) {
    container.innerHTML = '<div class="loading-state">No nodes currently registered. Start an agent node daemon!</div>';
    return;
  }

  container.innerHTML = nodes.map(node => {
    const isPreempted = node.control_mode === 'YIELDED_PASSIVE' || node.status === 'PREEMPTED';
    const isOffline = node.status === 'OFFLINE';

    const cardClass = isOffline ? 'node-card offline' : (isPreempted ? 'node-card preempted' : 'node-card');
    const badgeClass = isPreempted ? 'control-mode-badge badge-preempted' : 'control-mode-badge badge-full-control';
    const modeText = isPreempted ? '🟡 PREEMPTED (HUMAN)' : '🟢 FULL CONTROL';

    const capsHtml = (node.capabilities || []).map(c => `<span class="cap-pill">${escapeHtml(c)}</span>`).join('');

    return `
      <div class="node-card ${cardClass}">
        <div class="node-header">
          <div class="node-avatar">${node.persona_avatar || '🤖'}</div>
          <div class="node-title-box">
            <h4>${escapeHtml(node.persona_name || node.name)}</h4>
            <small>${escapeHtml(node.node_id)} • ${escapeHtml(node.hostname)}</small>
          </div>
          <span class="${badgeClass}">${modeText}</span>
        </div>
        <div class="node-details">
          <div><strong>Role:</strong> ${escapeHtml(node.persona_role || 'Worker')}</div>
          <div><strong>Platform:</strong> ${escapeHtml(node.platform_name)} (${node.ip})</div>
          <div><strong>Load:</strong> CPU ${node.cpu_percent.toFixed(1)}% | RAM ${node.memory_percent.toFixed(1)}%</div>
          <div><strong>Current Task:</strong> ${node.current_task_id ? `<span class="tag-pill">${escapeHtml(node.current_task_id)}</span>` : '<span style="color:var(--text-dim)">Idle</span>'}</div>
        </div>
        <div class="node-caps">${capsHtml}</div>
        <div class="node-actions">
          ${isPreempted ? `
            <button class="btn btn-primary" style="flex:1;font-size:0.8rem;padding:6px;" onclick="setNodeControl('${node.node_id}', 'FULL_CONTROL')">
              Reclaim Control
            </button>
          ` : `
            <button class="btn btn-warning" style="flex:1;font-size:0.8rem;padding:6px;" onclick="setNodeControl('${node.node_id}', 'YIELDED_PASSIVE')">
              Force Yield to Human
            </button>
          `}
        </div>
      </div>
    `;
  }).join('');
}

function renderGoalsAndTasks(goals, tasks) {
  const container = document.getElementById('goals-container');
  if (!goals || goals.length === 0) {
    container.innerHTML = '<div class="loading-state">No goals active. Choose a template above to launch an autonomous DAG pipeline!</div>';
    return;
  }

  const taskMap = {};
  tasks.forEach(t => { taskMap[t.id] = t; });

  container.innerHTML = goals.map(goal => {
    const goalTasks = (goal.task_ids || []).map(id => taskMap[id]).filter(Boolean);
    const completedCount = goalTasks.filter(t => t.status === 'COMPLETED').length;
    const progressPct = goalTasks.length > 0 ? (completedCount / goalTasks.length) * 100 : 0;

    const tasksHtml = goalTasks.map(t => {
      let icon = '⏳';
      if (t.status === 'COMPLETED') icon = '✅';
      else if (t.status === 'RUNNING') icon = '⚡';
      else if (t.status === 'PREEMPTED') icon = '⏸️';
      else if (t.status === 'FAILED') icon = '❌';

      return `
        <div class="task-item ${t.status}">
          <span class="task-status-icon">${icon}</span>
          <div class="task-info">
            <h5>${escapeHtml(t.title)}</h5>
            <small>${escapeHtml(t.description)}</small>
            ${t.dependencies && t.dependencies.length > 0 ? `<div class="task-deps">Deps: ${t.dependencies.join(', ')}</div>` : ''}
          </div>
          <div style="text-align:right">
            <span class="cap-pill">${t.status}</span>
            <div style="font-size:0.75rem;color:var(--text-dim);margin-top:4px;">
              ${t.assigned_node_id ? `Assigned: ${t.assigned_node_id}` : 'Unassigned'}
            </div>
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="goal-card">
        <div class="goal-header">
          <div>
            <h3>${escapeHtml(goal.title)}</h3>
            <p style="color:var(--text-muted);font-size:0.85rem;">${escapeHtml(goal.description || '')}</p>
          </div>
          <span class="tag-pill">${goal.status} (${completedCount}/${goalTasks.length} tasks)</span>
        </div>
        <div class="tasks-dag-list">
          ${tasksHtml}
        </div>
      </div>
    `;
  }).join('');
}

function renderAuditLogs(logs) {
  const tbody = document.getElementById('audit-table-body');
  if (!logs || logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-dim);">No preemption signals recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = logs.map(l => `
    <tr>
      <td>${new Date(l.timestamp * 1000).toLocaleTimeString()}</td>
      <td><code>${escapeHtml(l.node_id)}</code></td>
      <td><span class="tag-pill">${escapeHtml(l.signal_type)}</span></td>
      <td>${escapeHtml(l.username || 'n/a')}</td>
      <td>${escapeHtml(l.details)}</td>
    </tr>
  `).join('');
}

function renderTemplates(tmpls) {
  const container = document.getElementById('template-buttons');
  const modalSelect = document.getElementById('modal-template-select');

  container.innerHTML = tmpls.map(t => `
    <button class="btn btn-secondary" onclick="quickLaunchGoal('${t.template_id}')">
      ➕ ${escapeHtml(t.title)}
    </button>
  `).join('');

  modalSelect.innerHTML = tmpls.map(t => `
    <option value="${t.template_id}">${escapeHtml(t.title)}</option>
  `).join('');
}

// User Actions
async function reactToPost(postId, emoji) {
  try {
    await fetch(`/api/feed/${postId}/react`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ emoji: emoji, author_id: 'ceo-001' })
    });
    fetchFeed();
  } catch (e) {
    console.error('Error reacting to post:', e);
  }
}

async function promptComment(postId) {
  const text = prompt('Enter your reply as Human CEO:');
  if (!text) return;
  try {
    await fetch(`/api/feed/${postId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        author_id: 'ceo-001',
        author_name: 'CEO / Human Operator',
        author_role: 'Founder & CEO',
        author_avatar: '👑',
        content: text
      })
    });
    fetchFeed();
  } catch (e) {
    console.error('Error replying:', e);
  }
}

async function setNodeControl(nodeId, mode) {
  try {
    await fetch(`/api/nodes/${nodeId}/control_mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ control_mode: mode })
    });
    fetchNodes();
    fetchAuditLogs();
  } catch (e) {
    console.error('Error setting control mode:', e);
  }
}

async function quickLaunchGoal(templateId) {
  try {
    await fetch('/api/goals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template_id: templateId })
    });
    fetchGoalsAndTasks();
    fetchStats();
    // Switch to DAG tab
    document.querySelector('[data-tab="dag-tab"]').click();
  } catch (e) {
    console.error('Error launching goal:', e);
  }
}

function insertTag(tag) {
  const input = document.getElementById('ceo-post-input');
  input.value += (input.value ? ' ' : '') + tag;
  input.focus();
}

function setupEventListeners() {
  document.getElementById('btn-refresh').addEventListener('click', () => {
    fetchAllData();
  });

  document.getElementById('btn-send-ceo-post').addEventListener('click', async () => {
    const input = document.getElementById('ceo-post-input');
    const content = input.value.trim();
    if (!content) return;

    try {
      await fetch('/api/feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author_id: 'ceo-001',
          author_name: 'CEO / Human Operator',
          author_role: 'Founder & CEO',
          author_avatar: '👑',
          content: content,
          is_ceo: true,
          mood: 'hyped'
        })
      });
      input.value = '';
      fetchFeed();
    } catch (e) {
      console.error('Error sending CEO post:', e);
    }
  });

  // Simulate human activity trigger
  document.getElementById('btn-simulate-human').addEventListener('click', async () => {
    if (cachedNodes.length === 0) {
      alert('No active nodes to simulate preemption on!');
      return;
    }
    const targetNode = cachedNodes[0];
    const nextMode = targetNode.control_mode === 'FULL_CONTROL' ? 'USER_DETECTED' : 'USER_IDLE';

    await fetch('/api/preemption/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_id: targetNode.node_id,
        signal_type: nextMode,
        username: 'human_at_workstation',
        details: 'Simulated keyboard/mouse interaction'
      })
    });
    fetchNodes();
    fetchAuditLogs();
  });

  // Modal handlers
  const modal = document.getElementById('goal-modal');
  document.getElementById('btn-launch-goal-modal').addEventListener('click', () => {
    modal.style.display = 'flex';
  });
  document.getElementById('btn-close-modal').addEventListener('click', () => {
    modal.style.display = 'none';
  });
  document.getElementById('btn-cancel-modal').addEventListener('click', () => {
    modal.style.display = 'none';
  });
  document.getElementById('btn-confirm-goal').addEventListener('click', async () => {
    const templateId = document.getElementById('modal-template-select').value;
    const title = document.getElementById('modal-goal-title').value.trim();
    modal.style.display = 'none';
    try {
      await fetch('/api/goals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_id: templateId, title: title || undefined })
      });
      fetchGoalsAndTasks();
      document.querySelector('[data-tab="dag-tab"]').click();
    } catch (e) {
      console.error('Error launching goal from modal:', e);
    }
  });
}

// Helpers
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function timeAgo(timestamp) {
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
