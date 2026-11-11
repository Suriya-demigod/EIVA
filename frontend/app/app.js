import { api, json, streamChat } from "./api.mjs";
import { setConversation, state } from "./state.mjs";

const view = document.querySelector("#view");
const toast = document.querySelector("#toast");
let toastTimer;
let commonSignature = "";

const esc = (value = "") => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const dateLabel = (value) => value ? new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Just now";
const badge = (status) => `<span class="badge ${["completed", "registered", "approved"].includes(status) ? "good" : ["running", "queued", "pending"].includes(status) ? "warn" : ["failed", "cancelled", "denied"].includes(status) ? "bad" : "blue"}">${esc(status)}</span>`;
const empty = (title, message) => `<div class="empty"><strong>${esc(title)}</strong>${esc(message)}</div>`;
function notify(message, error = false) { toast.textContent = message; toast.classList.toggle("error", error); toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("show"), 3800); }
function pageHeading(title, subtitle, actions = "") { return `<div class="page-heading"><div><div class="eyebrow">EIVA / WORKSPACE</div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`; }
function setConnection(ok) { document.querySelector("#connection-dot").className = ok ? "online" : "offline"; document.querySelector("#connection-label").textContent = ok ? "All systems ready" : "API unavailable"; }
function navigate(page) {
  state.page = page;
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => item.classList.toggle("active", item.dataset.page === page));
  const title = ({ overview: "Overview", chat: "Chat", tasks: "Tasks", knowledge: "Knowledge", memory: "Memory", vision: "Vision", settings: "Settings" })[page] || "Overview";
  document.querySelector("#page-title").textContent = title;
  document.querySelector("#sidebar").classList.remove("open");
  render();
}
function render() {
  const renderers = { overview: renderOverview, chat: renderChat, tasks: renderTasks, knowledge: renderKnowledge, memory: renderMemory, vision: renderVision, settings: renderSettings };
  (renderers[state.page] || renderOverview)();
  view.focus({ preventScroll: true });
}
function waveMarkup() { return Array.from({ length: 31 }, (_, i) => `<i style="--h:${8 + ((i * 13 + 7) % 25)}px"></i>`).join(""); }
function taskCards(items = state.tasks) {
  if (!items.length) return empty("No tasks in this workspace", "Start a research or coding task to see progress here.");
  return items.map((task) => `<article class="task-card"><div class="task-card-head"><div><strong>${esc(task.workflow)} workflow</strong><div class="activity-main"><span>${dateLabel(task.created_at)}</span></div></div>${badge(task.status)}</div><p>${esc(task.description)}</p><div class="progress-track"><i style="width:${Number(task.progress_percent) || 0}%"></i></div><div class="task-meta"><span>${Number(task.progress_percent) || 0}% complete</span><span>${esc(String(task.id).slice(0, 8))}</span></div>${["queued", "running"].includes(task.status) ? `<div class="task-actions"><button class="button subtle" data-cancel-task="${esc(task.id)}">Cancel task</button></div>` : task.error ? `<div class="field-help" style="color:#eda5a5;margin-top:8px">${esc(task.error)}</div>` : ""}</article>`).join("");
}
function approvalCards() {
  if (!state.approvals.length) return empty("Nothing needs your approval", "Consequential actions appear here before EIVA carries them out.");
  return state.approvals.map((item) => `<article class="approval-card"><div class="task-card-head"><strong>${esc(item.tool_name)}</strong><span class="badge warn">Review</span></div><p>${esc(item.summary)}</p><div class="field-help">Task ${esc(String(item.task_id).slice(0, 8))} · requested ${dateLabel(item.created_at)}</div><div class="approval-actions" style="margin-top:12px"><button class="button primary" data-approval="${esc(item.id)}" data-approved="true">Approve action</button><button class="button danger" data-approval="${esc(item.id)}" data-approved="false">Deny</button></div></article>`).join("");
}
async function refreshCommon() {
  const results = await Promise.allSettled([api("/tasks"), api("/approvals"), api("/agents"), api("/voice/status")]);
  if (results[0].status === "fulfilled") state.tasks = results[0].value.items || [];
  if (results[1].status === "fulfilled") state.approvals = results[1].value.items || [];
  if (results[2].status === "fulfilled") state.agents = results[2].value.items || [];
  if (results[3].status === "fulfilled") state.voiceEnabled = Boolean(results[3].value.enabled);
  setConnection(results.some((item) => item.status === "fulfilled"));
  const active = state.tasks.filter((task) => ["queued", "running"].includes(task.status)).length;
  const count = document.querySelector("#task-count"); count.textContent = active; count.classList.toggle("hidden", active === 0);
  updateTaskSubscriptions();
  const signature = JSON.stringify([state.tasks, state.approvals, state.agents, state.voiceEnabled]);
  if (signature !== commonSignature && ["overview", "tasks"].includes(state.page)) render();
  commonSignature = signature;
}
function updateTaskSubscriptions() {
  const activeIds = new Set(state.tasks.filter((task) => ["queued", "running"].includes(task.status)).map((task) => task.id));
  for (const [id, source] of state.events) if (!activeIds.has(id)) { source.close(); state.events.delete(id); }
  for (const id of activeIds) {
    if (state.events.has(id)) continue;
    const source = new EventSource(`${API}/tasks/${id}/events`); state.events.set(id, source);
    ["task.progress", "task.completed", "task.failed", "task.cancelled", "approval.requested", "approval.decided"].forEach((kind) => source.addEventListener(kind, (event) => {
      if (kind === "approval.requested") notify("A task is waiting for your approval.");
      if (kind.startsWith("task.")) refreshCommon();
      if (kind.startsWith("approval.")) refreshCommon();
      if (kind === "task.progress" && state.page === "tasks") refreshCommon();
      try { const parsed = JSON.parse(event.data); if (parsed.payload?.message && kind === "task.progress") document.title = `EIVA · ${parsed.payload.message}`; } catch { /* Events without optional details are still valid. */ }
    }));
    source.onerror = () => { source.close(); state.events.delete(id); };
  }
}
function renderOverview() {
  const activeCount = state.tasks.filter((task) => ["queued", "running"].includes(task.status)).length;
  const doneCount = state.tasks.filter((task) => task.status === "completed").length;
  const agentRows = state.agents.length ? state.agents.map((agent) => `<div class="agent-row"><div class="agent-symbol">${agent.name === "researcher" ? "⌕" : agent.name === "developer" ? "⌘" : agent.name === "browser" ? "◉" : "✳"}</div><div class="agent-info"><strong>${esc(agent.name)}</strong><span>${esc(agent.model_role)} · ${esc(agent.description)}</span></div>${badge(agent.status)}</div>`).join("") : empty("Agent registry is unavailable", "Check that the API is running.");
  const recentTasks = taskCards(state.tasks.slice(0, 2));
  view.innerHTML = `${pageHeading("A little more flow, a lot less friction.", "Your private assistant workspace is ready. Pick up a conversation or put EIVA to work.", `<button class="button subtle" data-page="knowledge">+ Add knowledge</button><button class="button primary" data-page="chat">Start a conversation <span aria-hidden="true">↗</span></button>`)}
    <div class="grid overview-grid"><div><section class="card hero-card"><div class="hero-copy"><div class="eyebrow">YOUR ASSISTANT, IN SYNC</div><h1>Good to have you<br/>back, <em>let’s get to it.</em></h1><p>Ask a question, start a task, or bring your own knowledge. EIVA keeps the moving parts in one calm place.</p></div><div class="hero-bottom"><button class="button primary" data-page="chat">Open chat <span>↗</span></button><button class="button subtle" data-page="tasks">View tasks</button></div><div class="hero-orbit">✳</div></section>
      <div class="metric-grid"><div class="metric"><div class="metric-label">ACTIVE TASKS <span class="metric-icon">◇</span></div><div class="metric-value">${activeCount}</div><div class="metric-note">in progress now</div></div><div class="metric"><div class="metric-label">COMPLETED <span class="metric-icon">✓</span></div><div class="metric-value">${doneCount}</div><div class="metric-note">in recent history</div></div><div class="metric"><div class="metric-label">APPROVALS <span class="metric-icon">⌑</span></div><div class="metric-value">${state.approvals.length}</div><div class="metric-note">waiting on your review</div></div></div>
      <section class="card" style="margin-top:15px"><div class="card-title"><h2>Recent work</h2><button class="small-link" data-page="tasks">See all →</button></div><div class="task-list">${recentTasks}</div></section>
      </div><div class="stack"><section class="card status-card"><div class="card-title"><h2>Assistant status</h2><span class="badge good">Ready</span></div><div class="status-line"><div class="status-emblem">✳</div><div class="status-text"><strong>EIVA is standing by</strong><span>Local workspace · Groq model router</span></div><i class="status-pulse"></i></div><div class="status-details"><span>Voice interface</span><b>${state.voiceEnabled ? "Enabled" : "Off by default"}</b></div></section>
      <section class="card"><div class="card-title"><h2>Voice studio</h2><button class="small-link" onclick="location.href='/voice-ui/'">Open ↗</button></div><div class="voice-card"><div class="status-emblem">♫</div><div class="voice-copy"><strong>${state.voiceEnabled ? "Ready when you are" : "Voice is switched off"}</strong><span>${state.voiceEnabled ? "Start a private voice session" : "Enable it in your local settings"}</span></div><div class="wave" aria-hidden="true">${waveMarkup()}</div></div></section>
      <section class="card"><div class="card-title"><h2>Agent team</h2><span class="badge blue">${state.agents.length} registered</span></div><div class="agent-list">${agentRows}</div></section>
      <section class="card"><div class="card-title"><h2>Needs your attention</h2><span class="badge ${state.approvals.length ? "warn" : "good"}">${state.approvals.length} pending</span></div><div class="approval-list">${approvalCards()}</div></section></div></div>`;
}
function renderChat() {
  view.innerHTML = `${pageHeading("Chat with EIVA", "A focused space for questions, ideas, and follow-through.", `<button class="button subtle" id="new-conversation">New conversation</button>`)}
    <div class="chat-layout"><section class="card chat-panel"><div class="chat-messages" id="messages"><div class="chat-welcome"><div class="welcome-mark">✳</div><h2>What’s on your mind?</h2><p>Ask a question or give EIVA something to work through. Your conversation stays in this local workspace.</p><div class="suggestions"><button class="suggestion">Help me plan my week</button><button class="suggestion">Summarize my project notes</button><button class="suggestion">Explain a tricky idea</button></div></div></div><form id="chat-form"><div class="chat-compose"><textarea id="chat-input" rows="1" maxlength="16000" placeholder="Message EIVA…" aria-label="Message EIVA"></textarea><button class="button primary" id="send-chat" type="submit">Send ↑</button></div><div class="compose-note">Enter to send · Shift + Enter for a new line · EIVA may make mistakes, check important details.</div></form></section>
    <aside class="chat-side"><section class="card"><div class="card-title"><h2>Connected capabilities</h2></div><div class="context-item"><i></i> Conversation memory <span style="margin-left:auto;color:#6f8190">Local</span></div><div class="context-item"><i></i> Groq model router <span style="margin-left:auto;color:#6f8190">Ready</span></div><div class="context-item"><i style="background:${state.voiceEnabled ? "var(--mint)" : "#708090"}"></i> Voice interface <span style="margin-left:auto;color:#6f8190">${state.voiceEnabled ? "On" : "Off"}</span></div><button class="button subtle" style="width:100%;margin-top:8px" onclick="location.href='/voice-ui/'">Open voice studio ↗</button></section><section class="card"><div class="card-title"><h2>Task workspace</h2></div><p class="field-help" style="line-height:1.7">Need EIVA to work through a multi-step request? Start a tracked research or coding task and follow its progress.</p><button class="button subtle" data-page="tasks">Open task monitor →</button></section></aside></div>`;
  loadConversation();
  document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => { document.querySelector("#chat-input").value = button.textContent; document.querySelector("#chat-input").focus(); }));
  document.querySelector("#chat-form").addEventListener("submit", sendChat);
  document.querySelector("#chat-input").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); document.querySelector("#chat-form").requestSubmit(); } });
  document.querySelector("#new-conversation").addEventListener("click", () => { setConversation(null); renderChat(); });
}
function addMessage(role, text = "") {
  const welcome = document.querySelector(".chat-welcome"); if (welcome) welcome.remove();
  const node = document.createElement("div"); node.className = `message ${role}`; node.innerHTML = `<div class="message-icon">${role === "user" ? "S" : "✳"}</div><div class="message-body"></div>`; node.querySelector(".message-body").textContent = text;
  document.querySelector("#messages").append(node); node.scrollIntoView({ block: "nearest" }); return node.querySelector(".message-body");
}
function loadConversation() {
  if (!state.conversationId) return;
  // History remains server-owned; this marker avoids implying older turns were lost after reload.
  const messages = document.querySelector("#messages");
  messages.innerHTML = `<div class="chat-welcome"><div class="welcome-mark">↻</div><h2>Conversation resumed</h2><p>Continue the saved conversation. Earlier turns remain in EIVA’s context, but are not displayed in this view.</p></div>`;
}
async function sendChat(event) {
  event.preventDefault(); const input = document.querySelector("#chat-input"); const message = input.value.trim(); if (!message) return;
  input.value = ""; input.disabled = true; const send = document.querySelector("#send-chat"); send.disabled = true;
  addMessage("user", message); const answer = addMessage("assistant", ""); answer.textContent = "Thinking…";
  try {
    answer.textContent = "";
    const completion = await streamChat(message, state.conversationId, (delta) => {
      answer.textContent += delta;
      answer.parentElement.scrollIntoView({ block: "nearest" });
    });
    setConversation(completion.conversation_id);
    document.querySelector("#footer-model").textContent = `${completion.model} · Conversation saved`;
    if (!answer.textContent.trim()) answer.textContent = "EIVA returned an empty response.";
  } catch (error) { answer.textContent = error.message || "Chat could not complete."; answer.style.color = "#efa1a1"; notify(error.message || "Chat request failed", true); }
  finally { input.disabled = false; send.disabled = false; input.focus(); }
}
function renderTasks() {
  view.innerHTML = `${pageHeading("Task monitor", "Start a workflow and follow its live progress, events, and decisions.", `<button class="button subtle" id="refresh-tasks">↻ Refresh</button>`)}
    <div class="grid two-column"><div class="stack"><section class="card"><div class="card-title"><h2>Active and recent tasks</h2><span class="badge blue">${state.tasks.length} total</span></div><div class="task-list">${taskCards()}</div></section><section class="card"><div class="card-title"><h2>Pending approvals</h2><span class="badge ${state.approvals.length ? "warn" : "good"}">${state.approvals.length} to review</span></div><div class="approval-list">${approvalCards()}</div></section></div>
    <div class="stack"><section class="card"><div class="card-title"><h2>Start a task</h2></div><form id="task-form"><div class="field"><label for="task-description">What should EIVA work on?</label><textarea id="task-description" maxlength="16000" required placeholder="Describe the outcome you want…"></textarea><span class="field-help">Tasks run in the background. You can cancel them at any time.</span></div><div class="field"><label for="task-workflow">Workflow</label><select id="task-workflow"><option value="research">Research</option><option value="coding">Coding</option></select></div><button class="button primary" type="submit">Start workflow →</button></form></section>
    <section class="card"><div class="card-title"><h2>Task events</h2><span class="badge blue">Live</span></div><p class="field-help" style="line-height:1.7">Progress and approval decisions refresh as the task runs. Open tasks remain available after a page refresh.</p></section></div></div>`;
  document.querySelector("#task-form").addEventListener("submit", createTask);
  document.querySelector("#refresh-tasks").addEventListener("click", refreshCommon);
}
async function createTask(event) {
  event.preventDefault(); const description = document.querySelector("#task-description").value.trim(); const workflow = document.querySelector("#task-workflow").value; if (!description) return;
  try { await api("/tasks", json({ description, workflow })); notify("Task started. EIVA will report progress here."); document.querySelector("#task-description").value = ""; await refreshCommon(); }
  catch (error) { notify(error.message, true); }
}
async function renderKnowledge() {
  view.innerHTML = `${pageHeading("Your knowledge base", "Index local documents, then ask questions grounded in their content.")}
    <div class="grid two-column"><div class="stack"><section class="card"><div class="card-title"><h2>Ask your sources</h2><span class="badge blue">Local search · Groq answer</span></div><form id="knowledge-search" class="search-form"><input id="knowledge-query" maxlength="2000" required placeholder="Ask something about your indexed documents…"/><button class="button primary">Ask</button></form><div id="knowledge-answer"></div></section><section class="card"><div class="card-title"><h2>Indexed sources</h2><button class="small-link" id="reload-sources">Refresh</button></div><div id="source-list" class="source-list">${empty("Loading sources", "Checking your local index…")}</div></section></div>
    <div class="stack"><section class="card"><div class="card-title"><h2>Index a document</h2></div><form id="index-form"><div class="field"><label for="index-path">Path on this machine</label><input id="index-path" maxlength="1000" required placeholder="data/knowledge/notes.md"/><span class="field-help">Only configured local knowledge roots can be indexed. Files stay on this machine.</span></div><button class="button primary">Index source</button></form></section><section class="card"><div class="card-title"><h2>How retrieval works</h2></div><div class="setting-row"><div><strong>Hybrid search</strong><span>Semantic vectors plus keyword matching</span></div><div class="setting-value">RRF</div></div><div class="setting-row"><div><strong>Embedding model</strong><span>Runs locally on your machine</span></div><div class="setting-value">BGE small</div></div></section></div></div>`;
  document.querySelector("#knowledge-search").addEventListener("submit", answerKnowledge);
  document.querySelector("#index-form").addEventListener("submit", indexKnowledge);
  document.querySelector("#reload-sources").addEventListener("click", loadSources);
  loadSources();
}
async function loadSources() {
  const target = document.querySelector("#source-list"); if (!target) return;
  try { const data = await api("/knowledge/sources"); target.innerHTML = data.length ? data.map((item) => `<article class="activity-item"><div class="activity-icon">▤</div><div class="activity-main"><strong title="${esc(item.source_path)}">${esc(item.document_name)}</strong><span>${esc(item.source_path)} · ${item.chunk_count} chunks</span></div><button class="button danger" data-delete-source="${esc(item.id)}">Remove</button></article>`).join("") : empty("No indexed sources yet", "Add a local file from a configured knowledge folder."); }
  catch (error) { target.innerHTML = empty("Could not load sources", error.message); }
}
async function answerKnowledge(event) {
  event.preventDefault(); const target = document.querySelector("#knowledge-answer"); const query = document.querySelector("#knowledge-query").value.trim(); target.innerHTML = `<div class="empty">Searching local sources…</div>`;
  try { const data = await api("/knowledge/answer", json({ query })); target.innerHTML = `<div class="answer-box">${esc(data.answer)}</div>${data.citations?.length ? `<div class="source-list" style="margin-top:12px">${data.citations.map((item) => `<div class="knowledge-hit"><div class="citation">[${esc(item.label)}] ${esc(item.document_name)} · ${esc(item.location || "document")}</div><div class="field-help" style="margin-top:5px">${esc(item.source_path)}${item.section ? ` · ${esc(item.section)}` : ""}</div></div>`).join("")}</div>` : empty("No source citations", "Index relevant documents and try again.")}`; }
  catch (error) { target.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
}
async function indexKnowledge(event) {
  event.preventDefault(); const path = document.querySelector("#index-path").value.trim();
  try { const data = await api("/knowledge/index", json({ path })); notify(`Indexed ${data.indexed.length} source${data.indexed.length === 1 ? "" : "s"}.`); document.querySelector("#index-path").value = ""; loadSources(); }
  catch (error) { notify(error.message, true); }
}
function renderMemory() {
  view.innerHTML = `${pageHeading("Memory", "Facts you chose to save. Review or remove them whenever you like.")}
    <div class="grid two-column"><section class="card"><div class="card-title"><h2>Saved memories</h2><button class="small-link" id="reload-memories">Refresh</button></div><form class="search-form" id="memory-search"><input id="memory-query" maxlength="500" placeholder="Filter your memories…"/><button class="button subtle">Search</button></form><div id="memory-list" class="memory-list">${empty("Loading memories", "Reading your private memory store…")}</div></section><section class="card"><div class="card-title"><h2>Save a memory</h2></div><form id="memory-form"><div class="field"><label for="memory-content">What should EIVA remember?</label><textarea id="memory-content" maxlength="16000" required placeholder="A preference, project detail, or useful fact…"></textarea><span class="field-help">Memories are saved only when you submit this form.</span></div><div class="field"><label for="memory-tags">Tags <span class="field-help">(comma separated)</span></label><input id="memory-tags" maxlength="500" placeholder="work, preferences"/></div><div class="field"><label for="memory-importance">Importance</label><select id="memory-importance"><option value="3">Normal</option><option value="4">High</option><option value="5">Essential</option><option value="2">Low</option><option value="1">Minimal</option></select></div><button class="button primary">Save memory</button></form></section></div>`;
  document.querySelector("#memory-form").addEventListener("submit", createMemory);
  document.querySelector("#memory-search").addEventListener("submit", (event) => { event.preventDefault(); loadMemories(document.querySelector("#memory-query").value.trim()); });
  document.querySelector("#reload-memories").addEventListener("click", () => loadMemories());
  loadMemories();
}
async function loadMemories(query = "") {
  const target = document.querySelector("#memory-list"); if (!target) return;
  try { const data = await api(`/memories?limit=100${query ? `&query=${encodeURIComponent(query)}` : ""}`); target.innerHTML = data.items.length ? data.items.map((item) => `<article class="memory-card"><p>${esc(item.content)}</p><div class="memory-tags">${item.tags.map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div><div class="memory-card-foot"><span class="field-help">Importance ${item.importance} · ${dateLabel(item.created_at)}</span><button class="button danger" data-delete-memory="${esc(item.id)}">Delete</button></div></article>`).join("") : empty("No memories found", query ? "Try another search or save a new memory." : "Save a fact when you want EIVA to remember it."); }
  catch (error) { target.innerHTML = empty("Could not load memories", error.message); }
}
async function createMemory(event) {
  event.preventDefault(); const content = document.querySelector("#memory-content").value.trim(); const tags = document.querySelector("#memory-tags").value.split(",").map((tag) => tag.trim()).filter(Boolean);
  try { await api("/memories", json({ content, tags, importance: Number(document.querySelector("#memory-importance").value) })); notify("Memory saved to your local workspace."); document.querySelector("#memory-content").value = ""; document.querySelector("#memory-tags").value = ""; loadMemories(); }
  catch (error) { notify(error.message, true); }
}
function renderVision() {
  view.innerHTML = `${pageHeading("Vision", "Share an image with EIVA and get an answer about what’s in it.")}
    <div class="grid two-column"><section class="card"><div class="card-title"><h2>Image workspace</h2><span class="badge blue">JPEG · PNG · WebP</span></div><div id="vision-drop" class="vision-drop"><label for="vision-file"><div style="font-size:24px;color:#89e0c6">▧</div><strong>Choose an image to analyze</strong><span>Images are sent to the configured Groq vision model and are not stored by EIVA.</span><input id="vision-file" type="file" accept="image/jpeg,image/png,image/webp"/></label></div><div class="field" style="margin-top:15px"><label for="vision-question">What do you want to know?</label><textarea id="vision-question" maxlength="4000" placeholder="Describe this image…"></textarea></div><button id="analyze-image" class="button primary" disabled>Analyze image →</button><div id="vision-answer" style="margin-top:15px"></div></section>
    <aside class="stack"><section class="card"><div class="card-title"><h2>Screen analysis</h2><span class="badge warn">Task required</span></div><p class="field-help" style="line-height:1.7">Browser screenshots are analyzed inside a tracked task. Start a task first, then EIVA can capture and inspect its task-owned browser session.</p><button class="button subtle" data-page="tasks">Open task monitor →</button></section><section class="card"><div class="card-title"><h2>Privacy and limits</h2></div><div class="setting-row"><div><strong>Supported formats</strong><span>Validated image signatures</span></div><div class="setting-value">JPG / PNG / WebP</div></div><div class="setting-row"><div><strong>Upload limit</strong><span>Configured by your local instance</span></div><div class="setting-value">20 MB</div></div><div class="setting-row"><div><strong>Storage</strong><span>Image payload is not retained</span></div><div class="setting-value">Temporary</div></div></section></aside></div>`;
  document.querySelector("#vision-file").addEventListener("change", (event) => {
    const file = event.target.files[0]; if (!file) return;
    if (!(["image/jpeg", "image/png", "image/webp"].includes(file.type))) { notify("Choose a JPEG, PNG, or WebP image.", true); return; }
    state.visionFile = file; const drop = document.querySelector("#vision-drop"); drop.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="Selected image preview"/>`; document.querySelector("#analyze-image").disabled = false;
  });
  document.querySelector("#analyze-image").addEventListener("click", analyzeVision);
}
async function analyzeVision() {
  const file = state.visionFile; const question = document.querySelector("#vision-question").value.trim(); if (!file || !question) { notify("Choose an image and enter a question first.", true); return; }
  const target = document.querySelector("#vision-answer"); const button = document.querySelector("#analyze-image"); button.disabled = true; target.innerHTML = empty("Analyzing image", "Sending the image to EIVA’s configured vision model…");
  try { const result = await api(`/vision/analyze?question=${encodeURIComponent(question)}`, { method: "POST", headers: { "Content-Type": file.type }, body: file }); target.innerHTML = `<div class="answer-box">${esc(result.answer)}</div><div class="field-help" style="margin-top:7px">Model: ${esc(result.model)}</div>`; }
  catch (error) { target.innerHTML = empty("Image analysis failed", error.message); }
  finally { button.disabled = false; }
}
function renderSettings() {
  view.innerHTML = `${pageHeading("Settings", "Runtime information for this EIVA instance.")}
    <div class="grid two-column"><section class="card"><div class="card-title"><h2>Connection</h2><span class="badge good">Local</span></div><div class="setting-row"><div><strong>API endpoint</strong><span>Requests stay on this EIVA server</span></div><div class="setting-value">/api/v1</div></div><div class="setting-row"><div><strong>Model provider</strong><span>Used for chat, vision, and grounded answers</span></div><div class="setting-value">Groq</div></div><div class="setting-row"><div><strong>Embeddings</strong><span>Semantic retrieval is computed locally</span></div><div class="setting-value">BAAI / BGE small</div></div><div class="setting-row"><div><strong>Vector and keyword index</strong><span>Local SQLite storage</span></div><div class="setting-value">sqlite-vec + FTS5</div></div></section>
    <div class="stack"><section class="card"><div class="card-title"><h2>Feature availability</h2><button class="small-link" id="refresh-status">Refresh</button></div><div class="setting-row"><div><strong>Chat and streaming</strong><span>Shared model router</span></div><span class="badge good">Ready</span></div><div class="setting-row"><div><strong>Voice</strong><span>Explicitly enabled by local configuration</span></div>${badge(state.voiceEnabled ? "registered" : "disabled")}</div><div class="setting-row"><div><strong>Task approvals</strong><span>Consequential tools wait for your decision</span></div><span class="badge good">Interactive</span></div></section><section class="card"><div class="card-title"><h2>Voice configuration</h2></div><p class="field-help" style="line-height:1.7">Voice is ${state.voiceEnabled ? "enabled" : "disabled by default"}. To change it, update <code>EIVA_VOICE_ENABLED</code> in your private local environment and restart EIVA.</p><button class="button subtle" onclick="location.href='/voice-ui/'">Open voice studio ↗</button></section></div></div>`;
  document.querySelector("#refresh-status").addEventListener("click", refreshCommon);
}
async function handleClick(event) {
  const page = event.target.closest("[data-page]")?.dataset.page; if (page) { navigate(page); return; }
  const decisionButton = event.target.closest("[data-approval]");
  if (decisionButton) {
    decisionButton.disabled = true;
    try { await api(`/approvals/${decisionButton.dataset.approval}`, json({ approved: decisionButton.dataset.approved === "true" })); notify(decisionButton.dataset.approved === "true" ? "Action approved." : "Action denied."); await refreshCommon(); }
    catch (error) { notify(error.message, true); decisionButton.disabled = false; }
    return;
  }
  const cancelButton = event.target.closest("[data-cancel-task]");
  if (cancelButton) { cancelButton.disabled = true; try { await api(`/tasks/${cancelButton.dataset.cancelTask}/cancel`, { method: "POST" }); notify("Task cancellation requested."); await refreshCommon(); } catch (error) { notify(error.message, true); } return; }
  const memoryButton = event.target.closest("[data-delete-memory]");
  if (memoryButton) { memoryButton.disabled = true; try { await api(`/memories/${memoryButton.dataset.deleteMemory}`, { method: "DELETE" }); notify("Memory deleted."); loadMemories(document.querySelector("#memory-query")?.value || ""); } catch (error) { notify(error.message, true); memoryButton.disabled = false; } return; }
  const sourceButton = event.target.closest("[data-delete-source]");
  if (sourceButton) { sourceButton.disabled = true; try { await api(`/knowledge/sources/${sourceButton.dataset.deleteSource}`, { method: "DELETE" }); notify("Source removed from the local index."); loadSources(); } catch (error) { notify(error.message, true); sourceButton.disabled = false; } }
}
document.addEventListener("click", handleClick);
document.querySelector("#menu-toggle").addEventListener("click", () => document.querySelector("#sidebar").classList.toggle("open"));
document.addEventListener("keydown", (event) => { if ((event.metaKey || event.ctrlKey) && event.key === "1") navigate("chat"); if (event.key === "Escape") document.querySelector("#sidebar").classList.remove("open"); });
navigate("overview");
refreshCommon();
setInterval(refreshCommon, 8000);
