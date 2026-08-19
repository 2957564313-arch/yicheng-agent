const accessTokenKey = "yicheng_access_token";
const sessionModeKey = "yicheng_session_mode";
const originalFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = (resource, options = {}) => {
  const token = localStorage.getItem(accessTokenKey);
  const headers = new Headers(options.headers || {});
  const url = typeof resource === "string" ? resource : resource.url;
  if (token && new URL(url, globalThis.location.href).origin === location.origin) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return originalFetch(resource, { ...options, headers });
};

const $ = (selector) => document.querySelector(selector);
const queryInput = $("#query");
const submitButton = $("#submit");
const resetButton = $("#reset");
const modeSelect = $("#mode");
const timeline = $("#timeline");
const planTitle = $("#plan-title");
const resultSummary = $("#result-summary");
const resultRequest = $("#result-request");
const resultRequestText = $("#result-request-text");
const resultRequestInput = $("#result-request-input");
const resultEdit = $("#result-edit");
const resultRerun = $("#result-rerun");
const resultAddAgenda = $("#result-add-agenda");
const resultDetails = $("#result-details");
const resultConstraints = $("#result-constraints");
const resultConstraintTotal = $("#result-constraint-total");
const resultSources = $("#result-sources");
const resultQuickActions = $("#result-quick-actions");
const resultActionStatus = $("#result-action-status");
const resultCandidateActions = $("#result-candidate-actions");
const resultChangeSummary = $("#result-change-summary");
const taskStatuses = $("#task-statuses");
const answer = $("#answer");
const conversationStream = $("#conversation-stream");
const assistantActions = $("#assistant-actions");
const warnings = $("#warnings");
const freshness = $("#freshness");
const health = $("#health");
const saveState = $("#save-state");
const demoButtons = $("#demo-buttons");
const sidebarDemoButtons = $("#sidebar-demo-buttons");
const execution = $("#execution");
const constraints = $("#constraints");
const adjustment = $("#adjustment");
const diff = $("#diff");
const insights = $("#insights");
const debugContent = $("#debug-content");
const clock = $("#clock");
const memoryType = $("#memory-type");
const memoryValue = $("#memory-value");
const memorySave = $("#memory-save");
const memoryList = $("#memory-list");
const personalizationToggle = $("#personalization-toggle");
const personalizationReset = $("#personalization-reset");
const personalizationState = $("#personalization-state");
const timetableSummary = $("#timetable-summary");
const hduhelpToken = $("#hduhelp-token");
const hduhelpConnect = $("#hduhelp-connect");
const hduhelpDisconnect = $("#hduhelp-disconnect");
const hduhelpSync = $("#hduhelp-sync");
const hduhelpBadge = $("#hduhelp-badge");
const hduhelpState = $("#hduhelp-state");
const hduhelpConnectForm = $("#hduhelp-connect-form");
const hduhelpSyncForm = $("#hduhelp-sync-form");
const hduhelpDataSummary = $("#hduhelp-data-summary");
const timetableTermControls = $("#timetable-term-controls");
const timetableTermView = $("#timetable-term-view");
const campusName = $("#campus-name");
const campusCity = $("#campus-city");
const campusDiscover = $("#campus-discover");
const campusReset = $("#campus-reset");
const campusState = $("#campus-state");
const campusSummary = $("#campus-summary");
const weeklyDemoButtons = $("#weekly-demo-buttons");
const weeklyState = $("#weekly-state");
const weeklySummary = $("#weekly-summary");
const weeklyGrid = $("#weekly-grid");
const weeklyRisks = $("#weekly-risks");
const weeklyQuery = $("#weekly-query");
const weeklyStart = $("#weekly-start");
const weeklyGenerate = $("#weekly-generate");
const agendaState = $("#agenda-state");
const agendaDate = $("#agenda-date");
const agendaToday = $("#agenda-today");
const agendaRefresh = $("#agenda-refresh");
const agendaMetrics = $("#agenda-metrics");
const agendaList = $("#agenda-list");
const agendaReminders = $("#agenda-reminders");
const careSuggestions = $("#care-suggestions");
const reminderCourse = $("#reminder-course");
const reminderWakeup = $("#reminder-wakeup");
const reminderMeeting = $("#reminder-meeting");
const reminderActivity = $("#reminder-activity");
const reminderStudy = $("#reminder-study");
const reminderBedtime = $("#reminder-bedtime");
const reminderBedtimeEnabled = $("#reminder-bedtime-enabled");
const reminderEnable = $("#reminder-enable");
const reminderSave = $("#reminder-save");
const reminderState = $("#reminder-state");
const agendaExport = $("#agenda-export");
const accessGate = $("#access-gate");
const loginForm = $("#login-form");
const loginUsername = $("#login-username");
const loginPassword = $("#login-password");
const loginDisplayName = $("#login-display-name");
const loginDisplayNameField = $("#login-display-name-field");
const loginPasswordConfirm = $("#login-password-confirm");
const loginPasswordConfirmField = $("#login-password-confirm-field");
const loginUsernameLabel = $("#login-username-label");
const loginSubmit = $("#login-submit");
const accessTitle = $("#access-title");
const accessDescription = $("#access-description");
const authTabs = $(".access-tabs");
const authViewButtons = document.querySelectorAll("[data-auth-view]");
const loginMessage = $("#login-message");
const logoutButton = $("#logout");
const adjustmentPanel = $(".adjustment-panel");
const historySidebar = $("#history-sidebar");
const historyList = $("#history-list");
const historyEmpty = $("#history-empty");
const historyToggle = $("#history-toggle");
const historyClose = $("#history-close");
const toolsSidebar = $("#tools-sidebar");
const toolsToggle = $("#tools-toggle");
const toolsClose = $("#tools-close");
const drawerBackdrop = $("#drawer-backdrop");
const workspace = $(".workspace");
const composerColumn = $(".composer-column");
const quickAccess = $(".quick-access");
const contentColumn = $(".content-column");
const composerPanel = $(".composer-panel");
const assistantPanel = $(".assistant-panel");
const schedulePanel = $("#schedule-panel");
const scheduleState = $("#schedule-state");
const schedulePeriodLabel = $("#schedule-period-label");
const scheduleDayView = $("#schedule-day-view");
const scheduleWeekView = $("#schedule-week-view");
const scheduleMonthView = $("#schedule-month-view");
const schedulePrev = $("#schedule-prev");
const scheduleToday = $("#schedule-today");
const scheduleNext = $("#schedule-next");
const scheduleTabs = document.querySelectorAll("[data-schedule-view]");
const viewButtons = document.querySelectorAll("[data-view]");
const visualGrid = $(".visual-grid");
const weeklyPanel = $(".weekly-panel");
const agendaPanel = $(".agenda-panel");
let activeWorkspaceView = "chat";
let activeAccessMode = "";
let activeAuthView = "bootstrap";
let productEntryUsername = "";
let scheduleViewMode = "day";
let scheduleCursorDate = null;
let lastAgendaData = null;
let activeConversationQuery = "";
let activeConversationAnswer = "";
let lastResultQuery = "";
let lastResultData = null;
let pendingPlanCandidate = null;
let activePlanningNowOverride = null;
let consoleUserId = getOrCreateLocalIdentity(
  "yicheng_user_id",
  "visitor",
);
let consoleThreadId = getOrCreateLocalIdentity(
  "yicheng_thread_id",
  "thread",
);
const requestedThreadId = new URLSearchParams(location.search).get("thread_id");
if (/^[A-Za-z0-9_-]{1,128}$/.test(requestedThreadId || "")) {
  consoleThreadId = requestedThreadId;
  localStorage.setItem("yicheng_thread_id", requestedThreadId);
}
let lastSuggestedActions = [];
let lastDebugPayload = null;
let serverClockBaseMs = null;
let serverClockFetchedAtMs = null;
let currentCampusProfile = null;
const memorySnapshotKey = "yicheng_memory_snapshot";
const timetableSnapshotKey = "yicheng_timetable_snapshot";
const calendarSnapshotKey = "yicheng_calendar_snapshot";
const planSnapshotKey = "yicheng_current_plan_snapshot";
const planPublishedKey = "yicheng_published_plan_id";
const campusSnapshotKey = "yicheng_campus_snapshot";
const behaviorHistoryKey = "yicheng_behavior_history";
const suggestionFeedbackKey = "yicheng_suggestion_feedback";
const personalizationEnabledKey = "yicheng_personalization_enabled";
const shownReminderKey = "yicheng_shown_reminders";
const reminderSettingsSnapshotKey = "yicheng_reminder_settings_snapshot";
let currentReminderSettings = null;
let reminderPollTimer = null;
let serverConversationThreads = [];
let loadedMemories = [];
let editingMemoryKey = null;

function readLocalSnapshot(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLocalSnapshot(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

const dashboardIconPaths = {
  feasibility: '<path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><path d="m9 11 3 3L22 4"/>',
  tasks: '<rect width="14" height="16" x="5" y="4" rx="2"/><path d="M9 4V2h6v2M9 9h6M9 13h6"/>',
  end: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  buffer: '<path d="M6 2h12M6 22h12M8 2v5l4 5-4 5v5M16 2v5l-4 5 4 5v5"/>',
  travel: '<circle cx="12" cy="5" r="2"/><path d="m10 22 1-7-3-2 2-5 4 3 3 1M15 22l-2-7"/>',
  checks: '<path d="M12 22s8-3 8-10V5l-8-3-8 3v7c0 7 8 10 8 10"/><path d="m9 12 2 2 4-4"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V4H6.5A2.5 2.5 0 0 0 4 6.5z"/><path d="M8 7h8"/>',
  package: '<path d="m12 3 8 4-8 4-8-4 8-4Z"/><path d="m4 7 8 4 8-4v10l-8 4-8-4Z"/>',
  route: '<path d="M5 18a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"/><path d="M8 15h3a4 4 0 0 0 4-4v-1"/>',
  activity: '<circle cx="12" cy="5" r="2"/><path d="m5 22 3-8 3-2 2 3 4 1M10 12 8 9l3-2 4 3"/>',
  map: '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z"/><path d="M9 3v15M15 6v15"/>',
  building: '<path d="M3 21h18M6 21V5l6-3 6 3v16M9 9h.01M15 9h.01M9 13h.01M15 13h.01M10 21v-4h4v4"/>',
  cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.7-9H17.5a4.5 4.5 0 1 1 0 9Z"/>',
  calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
};

function dashboardIcon(name, className = "") {
  const paths = dashboardIconPaths[name] || dashboardIconPaths.tasks;
  return `<svg class="${escapeHtml(className)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
}

function renderConversationHistory() {
  if (!historyList || !historyEmpty) return;
  historyEmpty.hidden = serverConversationThreads.length > 0;
  historyList.innerHTML = serverConversationThreads.map((item) => `
      <div class="history-entry ${item.parent_thread_id ? "history-branch" : ""}">
        <a class="history-item ${item.id === consoleThreadId ? "active" : ""}" href="/?thread_id=${encodeURIComponent(item.id)}" data-thread-id="${escapeHtml(item.id)}" aria-label="打开对话：${escapeHtml(item.title || "未命名对话")}">
          <strong>${escapeHtml(item.title || "未命名对话")}</strong>
          <small>${item.parent_thread_id ? "分支 · " : ""}${escapeHtml(item.last_message || `${item.message_count || 0} 条消息`)}</small>
        </a>
        <button class="history-menu-trigger" type="button" data-thread-menu-toggle aria-label="更多对话操作" aria-haspopup="menu" aria-expanded="false">•••</button>
        <div class="history-item-menu" role="menu" hidden>
          <button type="button" role="menuitem" data-thread-rename="${escapeHtml(item.id)}" data-thread-title="${escapeHtml(item.title || "未命名对话")}">重命名</button>
          <button type="button" role="menuitem" data-thread-delete="${escapeHtml(item.id)}" data-thread-title="${escapeHtml(item.title || "未命名对话")}">删除</button>
        </div>
      </div>
  `).join("");
}

function appendConversationMessage(role, text, { messageId = "" } = {}) {
  if (!conversationStream || !String(text || "").trim()) return;
  const isUser = role === "user";
  conversationStream.hidden = false;
  conversationStream.insertAdjacentHTML(
    "beforeend",
    `<article class="conversation-message ${isUser ? "user-message" : "assistant-message"}" ${messageId ? `data-message-id="${escapeHtml(messageId)}"` : ""}>
      <span class="message-avatar" aria-hidden="true">${isUser ? "你" : "易"}</span>
      <div class="message-body">
        <p class="message-role">${isUser ? "你" : "易程智策"}</p>
        <div class="message-content">${escapeHtml(String(text))}</div>
        ${isUser && messageId ? `<button class="message-branch-action" type="button" data-branch-message="${escapeHtml(messageId)}">修改并新建分支</button>` : ""}
      </div>
    </article>`,
  );
}

function setConsoleThreadId(threadId) {
  if (!threadId) return;
  consoleThreadId = threadId;
  localStorage.setItem("yicheng_thread_id", threadId);
}

function attachMessageIdsToCurrentTurn(data) {
  const userMessage = [...(conversationStream?.querySelectorAll(".user-message") || [])]
    .findLast((item) => !item.dataset.messageId);
  if (userMessage && data?.user_message_id) {
    userMessage.dataset.messageId = data.user_message_id;
    userMessage.querySelector(".message-body")?.insertAdjacentHTML(
      "beforeend",
      `<button class="message-branch-action" type="button" data-branch-message="${escapeHtml(data.user_message_id)}">修改并新建分支</button>`,
    );
  }
}

async function loadConversationThreads() {
  const response = await fetch(`/api/v1/users/${consoleUserId}/threads`);
  const data = await response.json();
  if (!response.ok) throw data;
  serverConversationThreads = data;
  localStorage.removeItem("yicheng_conversation_history");
  renderConversationHistory();
}

async function renameConversationThread(threadId, currentTitle) {
  const title = window.prompt("给这条对话起个名字", currentTitle || "未命名对话");
  if (title === null || !title.trim() || title.trim() === currentTitle) return;
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/threads/${encodeURIComponent(threadId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim() }),
    },
  );
  const data = await response.json();
  if (!response.ok) throw data;
  await loadConversationThreads();
}

async function deleteConversationThread(threadId, title) {
  if (!window.confirm(`确定删除“${title || "未命名对话"}”吗？\n课表、偏好、记忆和已加入日程不会删除。`)) return;
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/threads/${encodeURIComponent(threadId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await response.json();
  if (threadId === consoleThreadId) newConversation?.click();
  await loadConversationThreads();
}

async function openConversationThread(threadId) {
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/threads/${encodeURIComponent(threadId)}`,
  );
  const data = await response.json();
  if (!response.ok) throw data;
  setConsoleThreadId(threadId);
  history.replaceState(
    null,
    "",
    `/?thread_id=${encodeURIComponent(threadId)}`,
  );
  clearConversationStream();
  const messages = data.messages || [];
  const finalAssistant = messages.at(-1)?.role === "assistant"
    ? messages.at(-1)
    : null;
  messages.slice(0, finalAssistant ? -1 : undefined).forEach((item) => {
    appendConversationMessage(item.role, item.content, { messageId: item.id });
  });
  const finalUser = [...messages].reverse().find((item) => item.role === "user");
  activeConversationQuery = finalUser?.content || "";
  activeConversationAnswer = finalAssistant?.content || "";
  lastResultQuery = activeConversationQuery;
  queryInput.value = "";
  setResultMode(false);
  answer.textContent = finalAssistant?.content || "这条分支还没有回复。";
  answer.classList.toggle("muted", !finalAssistant);
  freshness.innerHTML = '<span class="source-tag">服务端对话记录</span>';
  renderConversationHistory();
  closeDrawers();
}

function clearConversationStream() {
  conversationStream?.replaceChildren();
  if (conversationStream) conversationStream.hidden = true;
  activeConversationQuery = "";
  activeConversationAnswer = "";
}

function beginConversationTurn(query, { keepResultMode = false } = {}) {
  if (activeConversationQuery && activeConversationAnswer) {
    appendConversationMessage("assistant", activeConversationAnswer);
  }
  appendConversationMessage("user", query);
  activeConversationQuery = String(query || "").trim();
  lastResultQuery = activeConversationQuery;
  activeConversationAnswer = "";
  if (!keepResultMode) setResultMode(false);
  answer.textContent = "正在结合你的课表、时间和地点认真规划…";
  answer.classList.add("muted");
  assistantActions.innerHTML = "";
  freshness.innerHTML = "";
}

function completeConversationTurn(answerText) {
  if (!activeConversationQuery) return;
  activeConversationAnswer = String(answerText || "").trim();
}

function moveToolPanelsIntoWorkspace() {
  if (!contentColumn) return;
  [".hduhelp-panel", ".timetable-panel", ".memory-panel", ".execution-panel"]
    .map((selector) => document.querySelector(selector))
    .filter(Boolean)
    .forEach((panel) => {
      if (panel.parentElement !== contentColumn) contentColumn.append(panel);
    });
}

function setPanelHidden(panel, hidden) {
  if (panel) panel.hidden = hidden;
}

function setActiveWorkspaceView(view = "chat") {
  const supported = new Set([
    "chat", "schedule", "hduhelp", "timetable", "preferences", "weekly-planner",
  ]);
  activeWorkspaceView = supported.has(view) ? view : "chat";
  workspace?.setAttribute("data-active-view", activeWorkspaceView);
  viewButtons.forEach((button) => {
    const active = button.dataset.view === activeWorkspaceView
      || (activeWorkspaceView === "schedule" && button.dataset.view === "schedule");
    button.classList.toggle("active", active);
    if (button.dataset.view) button.setAttribute("aria-current", active ? "page" : "false");
  });

  const isChat = activeWorkspaceView === "chat";
  const hasPlanResult = document.body.classList.contains("has-plan-result");
  const isSchedule = activeWorkspaceView === "schedule";
  const isWeeklyPlanner = activeWorkspaceView === "weekly-planner";
  const isToolPage = ["hduhelp", "timetable", "preferences"].includes(activeWorkspaceView);

  conversationOutline?.classList.toggle("is-workspace-hidden", !isChat);

  setPanelHidden(composerColumn, !isChat);
  setPanelHidden(composerPanel, !isChat);
  setPanelHidden(quickAccess, !isChat);
  setPanelHidden(conversationStream, !isChat);
  setPanelHidden(assistantPanel, !isChat);
  setPanelHidden(visualGrid, !isChat || !hasPlanResult);
  setPanelHidden(document.querySelector(".adjustment-panel"), !isChat || !hasPlanResult);
  setPanelHidden(schedulePanel, !isSchedule);
  setPanelHidden(agendaPanel, true);
  setPanelHidden(weeklyPanel, !isWeeklyPlanner);
  setPanelHidden(document.querySelector(".hduhelp-panel"), activeWorkspaceView !== "hduhelp");
  setPanelHidden(document.querySelector(".timetable-panel"), activeWorkspaceView !== "timetable");
  setPanelHidden(document.querySelector(".memory-panel"), activeWorkspaceView !== "preferences");
  setPanelHidden(document.querySelector(".execution-panel"), true);
  if (isSchedule) renderScheduleViews();
  if (isToolPage) closeDrawers();
}

function scheduleDateValue(rawDate) {
  const [year, month, day] = String(rawDate).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function scheduleDateString(value) {
  return value.toISOString().slice(0, 10);
}

function scheduleShift(rawDate, offset, unit = "day") {
  const value = scheduleDateValue(rawDate);
  if (unit === "month") value.setUTCMonth(value.getUTCMonth() + offset);
  else value.setUTCDate(value.getUTCDate() + offset);
  return scheduleDateString(value);
}

function scheduleWeekStart(rawDate) {
  const value = scheduleDateValue(rawDate);
  const day = value.getUTCDay() || 7;
  value.setUTCDate(value.getUTCDate() - day + 1);
  return scheduleDateString(value);
}

function scheduleMonthStart(rawDate) {
  const value = scheduleDateValue(rawDate);
  value.setUTCDate(1);
  return scheduleDateString(value);
}

function scheduleMonthEnd(rawDate) {
  const value = scheduleDateValue(rawDate);
  value.setUTCMonth(value.getUTCMonth() + 1, 0);
  return scheduleDateString(value);
}

function scheduleItemsByDate() {
  return (lastAgendaData?.items || []).filter(
    (item) => item.kind !== "meal",
  ).reduce((result, item) => {
    const date = agendaItemDate(item);
    (result[date] ||= []).push(item);
    return result;
  }, {});
}

let scheduleCalendarContexts = {};

const conversationOutline = document.createElement("section");
conversationOutline.className = "conversation-outline";
conversationOutline.id = "conversation-outline";
conversationOutline.hidden = true;
conversationOutline.innerHTML = `
  <div class="conversation-outline-heading">
    <strong>快速定位</strong>
  </div>
  <nav id="conversation-outline-list" aria-label="本次对话快速定位"></nav>`;
document.body.append(conversationOutline);
const conversationOutlineList = conversationOutline.querySelector("#conversation-outline-list");
let conversationOutlineObserver;

function setConversationOutlineOpen(open) {
  conversationOutline.classList.toggle("is-open", open);
  toolsToggle?.setAttribute("aria-expanded", String(open));
}

conversationOutline.addEventListener("click", (event) => {
  if (
    window.matchMedia("(max-width: 900px)").matches
    && !conversationOutline.classList.contains("is-open")
  ) {
    event.preventDefault();
    event.stopPropagation();
    setConversationOutlineOpen(true);
  }
});
document.addEventListener("click", (event) => {
  if (
    conversationOutline.classList.contains("is-open")
    && !conversationOutline.contains(event.target)
    && event.target !== toolsToggle
  ) setConversationOutlineOpen(false);
});
conversationOutline.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setConversationOutlineOpen(false);
    toolsToggle?.focus();
  }
});

function conversationMessageLabel(message) {
  const body = message.querySelector(".message-body, .message-bubble") || message;
  const text = body.textContent.replace(/\s+/g, " ").trim();
  return text.length > 34 ? `${text.slice(0, 34)}…` : text || "未命名提问";
}

function setActiveConversationOutline(messageId) {
  conversationOutlineList.querySelectorAll("button").forEach((button) => {
    const active = button.dataset.messageTarget === messageId;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "true");
    else button.removeAttribute("aria-current");
  });
}

function syncConversationOutline() {
  if (!conversationStream || !conversationOutlineList) return;
  const messages = [...conversationStream.querySelectorAll(".conversation-message.user-message")];
  const hasMultipleTurns = messages.length > 1;
  conversationOutline.hidden = !hasMultipleTurns;
  if (toolsToggle) toolsToggle.hidden = !hasMultipleTurns;
  if (!hasMultipleTurns) setConversationOutlineOpen(false);
  conversationOutlineList.innerHTML = messages.map((message, index) => {
    const id = message.id || `conversation-turn-${index + 1}`;
    message.id = id;
    return `<button type="button" data-message-target="${escapeHtml(id)}"><strong>${escapeHtml(conversationMessageLabel(message))}</strong></button>`;
  }).join("");
  conversationOutlineList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.messageTarget);
      if (!target) return;
      if (document.body.classList.contains("has-plan-result")) setResultMode(false);
      window.requestAnimationFrame(() => {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("is-located");
        window.setTimeout(() => target.classList.remove("is-located"), 1200);
      });
      setActiveConversationOutline(target.id);
      setConversationOutlineOpen(false);
    });
  });
  if (messages.length) {
    setActiveConversationOutline(messages[messages.length - 1].id);
  }
  conversationOutlineObserver?.disconnect();
  conversationOutlineObserver = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => Math.abs(a.boundingClientRect.top) - Math.abs(b.boundingClientRect.top));
    if (visible[0]?.target?.id) setActiveConversationOutline(visible[0].target.id);
  }, { rootMargin: "-28% 0px -55% 0px", threshold: 0 });
  messages.forEach((message) => conversationOutlineObserver.observe(message));
}

if (conversationStream) {
  new MutationObserver(syncConversationOutline).observe(conversationStream, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  syncConversationOutline();
}

function scheduleCalendarBadge(date, includeName = false) {
  const context = scheduleCalendarContexts[date];
  if (!context || !["holiday", "adjusted_workday"].includes(context.day_type)) return "";
  const holiday = context.day_type === "holiday";
  const label = context.label || (holiday ? "法定节假日" : "待确认补课安排");
  return `<span class="schedule-calendar-badge ${holiday ? "holiday" : "workday"}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${holiday ? "休" : "补"}${includeName ? `<small>${escapeHtml(label)}</small>` : ""}</span>`;
}

function scheduleCalendarNotice(date) {
  const context = scheduleCalendarContexts[date];
  if (!context || !["holiday", "adjusted_workday"].includes(context.day_type)) return "";
  const holiday = context.day_type === "holiday";
  return `<div class="schedule-calendar-notice ${holiday ? "holiday" : "workday"}">${scheduleCalendarBadge(date)}<span><strong>${escapeHtml(context.label || (holiday ? "法定节假日" : "调休工作日"))}</strong>${holiday ? "法定节假日，常规课程不执行；如杭助同步到特殊安排，仍以杭助记录为准" : "调休工作日已标注，实际补课课程以杭助同步结果为准"}</span></div>`;
}

function scheduleItemMarkup(item, compact = false) {
  return `
    <article class="schedule-event ${escapeHtml(item.kind || "task")}" title="${escapeHtml(item.title || "日程")}">
      <time>${escapeHtml(timePart(item.start_at))}—${escapeHtml(timePart(item.end_at))}</time>
      <div><strong>${escapeHtml(item.title || "未命名安排")}</strong>${compact ? "" : `<small>${escapeHtml(item.location_name || (item.kind === "travel" ? "通勤时间" : "个人安排"))}</small>`}</div>
    </article>`;
}

function renderScheduleViews() {
  if (!schedulePanel || !scheduleCursorDate) return;
  const byDate = scheduleItemsByDate();
  const selected = scheduleCursorDate;
  const dayItems = (byDate[selected] || []).sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
  const today = shanghaiDateString();
  const startOfWeek = scheduleWeekStart(selected);
  const monthStart = scheduleMonthStart(selected);
  const monthEnd = scheduleMonthEnd(selected);
  const monthFirst = scheduleDateValue(monthStart);
  const firstWeekday = monthFirst.getUTCDay() || 7;
  const daysInMonth = Number(monthEnd.slice(-2));

  if (scheduleViewMode === "day") {
    schedulePeriodLabel.textContent = selected === today ? "今天" : `${selected.slice(5).replace("-", "月")}日`;
    scheduleDayView.innerHTML = scheduleCalendarNotice(selected) + (dayItems.length
      ? `<div class="schedule-day-timeline">${dayItems.map((item) => scheduleItemMarkup(item)).join("")}</div>`
      : `<div class="schedule-empty"><strong>今天还没有固定安排</strong><span>可以在对话中告诉我想完成什么，或把时间留给休息和临时变化。</span></div>`);
  }
  if (scheduleViewMode === "week") {
    const weekDates = Array.from({ length: 7 }, (_, index) => addWeeklyDays(startOfWeek, index));
    schedulePeriodLabel.textContent = `${startOfWeek.slice(5).replace("-", "月")}日 — ${weekDates[6].slice(5).replace("-", "月")}日`;
    scheduleWeekView.innerHTML = `<div class="schedule-week-grid">${weekDates.map((date) => {
      const items = (byDate[date] || []).sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
      const dateValue = scheduleDateValue(date);
      const weekday = "一二三四五六日"[dateValue.getUTCDay() === 0 ? 6 : dateValue.getUTCDay() - 1];
      return `<section class="schedule-week-day ${date === today ? "is-today" : ""}">
        <header><span>周${weekday}</span><strong>${date.slice(8)}<small>日</small></strong><em>${items.length ? `${items.length}项` : "空闲"}</em>${scheduleCalendarBadge(date, true)}</header>
        <div>${items.length ? items.map((item) => scheduleItemMarkup(item, true)).join("") : `<p class="schedule-empty-mini">留作弹性时间</p>`}</div>
      </section>`;
    }).join("")}</div>`;
  }
  if (scheduleViewMode === "month") {
    const monthLabel = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "long" }).format(scheduleDateValue(selected));
    schedulePeriodLabel.textContent = monthLabel;
    const cells = [];
    for (let index = 1; index < firstWeekday; index += 1) cells.push(`<div class="schedule-month-cell is-muted"></div>`);
    for (let day = 1; day <= daysInMonth; day += 1) {
      const date = `${monthStart.slice(0, 8)}${String(day).padStart(2, "0")}`;
      const items = byDate[date] || [];
      const calendarContext = scheduleCalendarContexts[date];
      const pendingMakeup = calendarContext?.day_type === "adjusted_workday" && calendarContext?.course_action !== "makeup";
      cells.push(`<button type="button" class="schedule-month-cell ${date === today ? "is-today" : ""} ${date === selected ? "is-selected" : ""} ${calendarContext?.day_type === "holiday" ? "is-holiday" : ""} ${pendingMakeup ? "is-workday" : ""}" data-schedule-date="${date}">
        <span class="schedule-month-date"><span>${day}</span>${scheduleCalendarBadge(date)}</span><small>${items.length ? `${items.length}项` : calendarContext?.label ? escapeHtml(calendarContext.label) : ""}</small><i>${items.slice(0, 3).map((item) => `<b class="${escapeHtml(item.kind || "task")}"></b>`).join("")}</i>
      </button>`);
    }
    scheduleMonthView.innerHTML = `<div class="schedule-month-weekdays">${"一二三四五六日".split("").map((day) => `<span>周${day}</span>`).join("")}</div><div class="schedule-month-grid">${cells.join("")}</div>`;
    scheduleMonthView.querySelectorAll("[data-schedule-date]").forEach((button) => {
      button.addEventListener("click", () => {
        scheduleCursorDate = button.dataset.scheduleDate;
        scheduleViewMode = "day";
        updateScheduleTabs();
        loadAgenda(scheduleCursorDate).catch((error) => renderDebug(error));
      });
    });
  }
  [scheduleDayView, scheduleWeekView, scheduleMonthView].forEach((panel) => {
    if (panel) panel.hidden = !panel.id.endsWith(`${scheduleViewMode}-view`);
  });
  if (scheduleState) scheduleState.textContent = `${dayItems.length} 项安排`;
}

function updateScheduleTabs() {
  scheduleTabs.forEach((button) => {
    const active = button.dataset.scheduleView === scheduleViewMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  renderScheduleViews();
}

function closeDrawers() {
  historySidebar?.classList.remove("mobile-open");
  toolsSidebar?.classList.remove("mobile-open");
  document.body.classList.remove("drawer-open");
  historyToggle?.setAttribute("aria-expanded", "false");
  toolsToggle?.setAttribute("aria-expanded", "false");
  setConversationOutlineOpen(false);
  if (drawerBackdrop) drawerBackdrop.hidden = true;
}

function openDrawer(sidebar, toggle) {
  if (!sidebar) return;
  const opening = !sidebar.classList.contains("mobile-open");
  historySidebar?.classList.remove("mobile-open");
  toolsSidebar?.classList.remove("mobile-open");
  if (!opening) {
    closeDrawers();
    return;
  }
  sidebar.classList.add("mobile-open");
  document.body.classList.add("drawer-open");
  historyToggle?.setAttribute("aria-expanded", String(sidebar === historySidebar));
  toolsToggle?.setAttribute("aria-expanded", String(sidebar === toolsSidebar));
  if (drawerBackdrop) drawerBackdrop.hidden = false;
  toggle?.focus();
}

function initializeWorkspaceNavigation() {
  moveToolPanelsIntoWorkspace();
  historyToggle?.addEventListener("click", () => openDrawer(historySidebar, historyToggle));
  toolsToggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    setConversationOutlineOpen(
      !conversationOutline.classList.contains("is-open"),
    );
  });
  historyClose?.addEventListener("click", closeDrawers);
  toolsClose?.addEventListener("click", closeDrawers);
  drawerBackdrop?.addEventListener("click", closeDrawers);

  function closeHistoryMenus(exceptEntry = null) {
    historyList?.querySelectorAll(".history-entry").forEach((entry) => {
      if (entry === exceptEntry) return;
      const trigger = entry.querySelector("[data-thread-menu-toggle]");
      const menu = entry.querySelector(".history-item-menu");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
      if (menu) menu.hidden = true;
    });
  }

  historyList?.addEventListener("click", (event) => {
    const menuTrigger = event.target.closest("[data-thread-menu-toggle]");
    if (menuTrigger) {
      event.preventDefault();
      event.stopPropagation();
      const entry = menuTrigger.closest(".history-entry");
      const menu = entry?.querySelector(".history-item-menu");
      if (!entry || !menu) return;
      const willOpen = menu.hidden;
      closeHistoryMenus(entry);
      menu.hidden = !willOpen;
      menuTrigger.setAttribute("aria-expanded", String(willOpen));
      if (willOpen) menu.querySelector("button")?.focus();
      return;
    }
    const renameButton = event.target.closest("[data-thread-rename]");
    const deleteButton = event.target.closest("[data-thread-delete]");
    if (renameButton || deleteButton) {
      event.preventDefault();
      event.stopPropagation();
      closeHistoryMenus();
      const action = renameButton
        ? renameConversationThread(
          renameButton.dataset.threadRename,
          renameButton.dataset.threadTitle,
        )
        : deleteConversationThread(
          deleteButton.dataset.threadDelete,
          deleteButton.dataset.threadTitle,
        );
      action.catch((error) => renderError(error));
      return;
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".history-entry")) closeHistoryMenus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeHistoryMenus();
  });

  conversationStream?.addEventListener("click", (event) => {
    const branchButton = event.target.closest("[data-branch-message]");
    if (!branchButton) return;
    const message = branchButton.closest(".conversation-message");
    if (!message) return;
    const existing = message.querySelector(".message-branch-editor");
    if (existing) {
      existing.remove();
      branchButton.hidden = false;
      return;
    }
    branchButton.hidden = true;
    const original = message.querySelector(".message-content")?.textContent || "";
    message.querySelector(".message-body")?.insertAdjacentHTML(
      "beforeend",
      `<form class="message-branch-editor">
        <label>修改这条提问并从这里开始新分支</label>
        <textarea maxlength="2000" required>${escapeHtml(original)}</textarea>
        <div><button type="button" class="ghost" data-branch-cancel>取消</button><button type="submit" class="primary">创建分支</button></div>
      </form>`,
    );
    message.querySelector(".message-branch-editor textarea")?.focus();
  });

  conversationStream?.addEventListener("click", (event) => {
    const cancel = event.target.closest("[data-branch-cancel]");
    if (!cancel) return;
    const message = cancel.closest(".conversation-message");
    message?.querySelector(".message-branch-editor")?.remove();
    const action = message?.querySelector(".message-branch-action");
    if (action) action.hidden = false;
  });

  conversationStream?.addEventListener("submit", async (event) => {
    const form = event.target.closest(".message-branch-editor");
    if (!form) return;
    event.preventDefault();
    const message = form.closest(".conversation-message");
    const query = form.querySelector("textarea")?.value.trim();
    const fromMessageId = message?.dataset.messageId;
    if (!query || !fromMessageId || submitButton.disabled) return;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    submit.textContent = "正在创建…";
    setLoading(true);
    try {
      const response = await fetch(
        `/api/v1/users/${consoleUserId}/threads/${encodeURIComponent(consoleThreadId)}/fork`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            from_message_id: fromMessageId,
            query,
            mode: modeSelect.value,
            publish_to_agenda: false,
            client_context: clientContextSnapshot(),
          }),
        },
      );
      const data = await response.json();
      if (!response.ok) throw data;
      setConsoleThreadId(data.branch.id);
      await loadConversationThreads();
      await openConversationThread(data.branch.id);
      renderResponse(data.response);
      saveState.textContent = "已保留原对话，并创建新的分支";
      saveState.classList.add("saved");
    } catch (error) {
      renderError(error);
      submit.disabled = false;
      submit.textContent = "创建分支";
    } finally {
      setLoading(false);
    }
  });

  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.scheduleMode) {
        scheduleViewMode = button.dataset.scheduleMode;
        updateScheduleTabs();
      }
      setActiveWorkspaceView(button.dataset.view);
      if (button.dataset.view === "schedule") {
        scheduleCursorDate = agendaDate?.value || shanghaiDateString();
        const rangeStart = scheduleViewMode === "month"
          ? scheduleMonthStart(scheduleCursorDate)
          : scheduleViewMode === "week"
            ? scheduleWeekStart(scheduleCursorDate)
            : scheduleCursorDate;
        const rangeEnd = scheduleViewMode === "month"
          ? scheduleMonthEnd(scheduleCursorDate)
          : addWeeklyDays(rangeStart, 6);
        loadAgendaRange(rangeStart, rangeEnd).catch((error) => renderDebug(error));
      }
      if (window.matchMedia("(max-width: 900px)").matches) closeDrawers();
    });
  });

  scheduleTabs.forEach((button) => {
    button.addEventListener("click", () => {
      scheduleViewMode = button.dataset.scheduleView || "day";
      updateScheduleTabs();
      if (!scheduleCursorDate) scheduleCursorDate = agendaDate?.value || shanghaiDateString();
      const rangeStart = scheduleViewMode === "month"
        ? scheduleMonthStart(scheduleCursorDate)
        : scheduleViewMode === "week"
          ? scheduleWeekStart(scheduleCursorDate)
          : scheduleCursorDate;
      const rangeEnd = scheduleViewMode === "month"
        ? scheduleMonthEnd(scheduleCursorDate)
        : addWeeklyDays(rangeStart, 6);
      loadAgendaRange(rangeStart, rangeEnd).catch((error) => renderDebug(error));
    });
  });
  schedulePrev?.addEventListener("click", () => {
    if (!scheduleCursorDate) scheduleCursorDate = agendaDate?.value || shanghaiDateString();
    scheduleCursorDate = scheduleShift(
      scheduleCursorDate,
      scheduleViewMode === "month" ? -1 : scheduleViewMode === "week" ? -7 : -1,
      scheduleViewMode === "month" ? "month" : "day",
    );
    const start = scheduleViewMode === "month" ? scheduleMonthStart(scheduleCursorDate) : scheduleViewMode === "week" ? scheduleWeekStart(scheduleCursorDate) : scheduleCursorDate;
    const end = scheduleViewMode === "month" ? scheduleMonthEnd(scheduleCursorDate) : addWeeklyDays(start, 6);
    loadAgendaRange(start, end).catch((error) => renderDebug(error));
  });
  scheduleNext?.addEventListener("click", () => {
    if (!scheduleCursorDate) scheduleCursorDate = agendaDate?.value || shanghaiDateString();
    scheduleCursorDate = scheduleShift(
      scheduleCursorDate,
      scheduleViewMode === "month" ? 1 : scheduleViewMode === "week" ? 7 : 1,
      scheduleViewMode === "month" ? "month" : "day",
    );
    const start = scheduleViewMode === "month" ? scheduleMonthStart(scheduleCursorDate) : scheduleViewMode === "week" ? scheduleWeekStart(scheduleCursorDate) : scheduleCursorDate;
    const end = scheduleViewMode === "month" ? scheduleMonthEnd(scheduleCursorDate) : addWeeklyDays(start, 6);
    loadAgendaRange(start, end).catch((error) => renderDebug(error));
  });
  scheduleToday?.addEventListener("click", () => {
    scheduleCursorDate = shanghaiDateString();
    const start = scheduleViewMode === "month" ? scheduleMonthStart(scheduleCursorDate) : scheduleViewMode === "week" ? scheduleWeekStart(scheduleCursorDate) : scheduleCursorDate;
    const end = scheduleViewMode === "month" ? scheduleMonthEnd(scheduleCursorDate) : addWeeklyDays(start, 6);
    loadAgendaRange(start, end).catch((error) => renderDebug(error));
  });

  setActiveWorkspaceView("chat");
}

function clientContextSnapshot() {
  const memories = readLocalSnapshot(memorySnapshotKey, []);
  const timetableData = readLocalSnapshot(timetableSnapshotKey, null);
  const previousPlan = readLocalSnapshot(planSnapshotKey, null);
  const campus = readLocalSnapshot(campusSnapshotKey, null);
  return {
    memories: memories.map((item) => ({
      category: item.category,
      key: item.key,
      label: item.label,
      value: item.value,
      enabled: item.enabled,
    })),
    timetable: timetableData?.entries?.length
      ? {
        name: timetableData.timetable?.name || "我的课表",
        term_start: timetableData.timetable?.term_start || null,
        term_end: timetableData.timetable?.term_end || null,
        enabled: timetableData.timetable?.enabled ?? true,
        entries: timetableData.entries,
      }
      : null,
    calendar_overrides: [],
    previous_plan: previousPlan,
    previous_plan_published: Boolean(
      previousPlan
      && localStorage.getItem(planPublishedKey) === previousPlan.id
    ),
    campus,
    personalization: personalizationSnapshot(),
  };
}

function personalContextPayload() {
  const context = clientContextSnapshot();
  return {
    schema_version: "1.0",
    thread_id: consoleThreadId,
    memories: context.memories,
    timetable: context.timetable,
    calendar_overrides: context.calendar_overrides,
    reminder_settings: currentReminderSettings
      || readLocalSnapshot(reminderSettingsSnapshotKey, null),
    current_plan: context.previous_plan,
    current_plan_published: context.previous_plan_published,
  };
}

function renderCampus(campus, { isDefault = false } = {}) {
  currentCampusProfile = campus;
  renderPersonalizationState();
  if (!campus) {
    campusState.textContent = "读取失败";
    campusSummary.textContent = "本校知识库暂时没有加载成功，请刷新重试。";
    campusSummary.classList.add("muted");
    campusReset.hidden = true;
    return;
  }
  const locationCount = campus.locations?.length
    ?? campus.location_count
    ?? 0;
  campusName.value = campus.display_name || "";
  campusCity.value = campus.search_city || "";
  campusState.textContent = isDefault ? "默认校园" : "已切换";
  campusState.classList.add("ready");
  campusSummary.classList.remove("muted");
  campusSummary.innerHTML = `
    <strong>${escapeHtml(campus.display_name)}</strong>
    <span>${locationCount} 个本校地点${
      isDefault
        ? "，并已配置本校知识规则。"
        : "。地点可用于路线计算；开放时间、节次和制度仍需导入本校知识包。"
    }</span>
  `;
  campusReset.hidden = isDefault;
}

async function loadCampus() {
  const saved = readLocalSnapshot(campusSnapshotKey, null);
  if (saved) {
    renderCampus(saved);
    return;
  }
  const response = await fetch("/api/v1/campuses/current");
  const data = await response.json();
  if (!response.ok) throw data;
  renderCampus(data, { isDefault: true });
}

campusDiscover.addEventListener("click", async () => {
  const schoolName = campusName.value.trim();
  if (!schoolName) {
    campusSummary.textContent = "请先填写学校名称，最好包含具体校区。";
    campusSummary.classList.remove("muted");
    return;
  }
  campusDiscover.disabled = true;
  campusDiscover.textContent = "正在查找校园地点…";
  campusSummary.textContent = "正在通过高德分类查找本校地点，请稍候。";
  try {
    const response = await fetch("/api/v1/campuses/discover", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        school_name: schoolName,
        city: campusCity.value.trim(),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw data;
    writeLocalSnapshot(campusSnapshotKey, data.campus);
    localStorage.removeItem(planSnapshotKey);
    renderCampus(data.campus);
    campusSummary.insertAdjacentHTML(
      "beforeend",
      `<small>${escapeHtml(data.coverage_note)}</small>`,
    );
  } catch (error) {
    campusState.textContent = "查找失败";
    campusSummary.textContent = error?.error?.message
      || "暂时无法查找这所学校，请检查名称和城市后重试。";
    campusSummary.classList.remove("muted");
  } finally {
    campusDiscover.disabled = false;
    campusDiscover.textContent = "查找这所学校";
  }
});

campusReset.addEventListener("click", async () => {
  localStorage.removeItem(campusSnapshotKey);
  localStorage.removeItem(planSnapshotKey);
  campusName.value = "";
  campusCity.value = "";
  campusState.classList.remove("ready");
  await loadCampus().catch((error) => renderDebug(error));
});

function getOrCreateLocalIdentity(storageKey, prefix) {
  const stored = localStorage.getItem(storageKey);
  if (stored) return stored;
  const randomPart = globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID().replaceAll("-", "")
    : `${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const value = `${prefix}_${randomPart}`.slice(0, 64);
  localStorage.setItem(storageKey, value);
  return value;
}

const personalCacheKeys = [
  "yicheng_conversation_history",
  "yicheng_thread_id",
  memorySnapshotKey,
  timetableSnapshotKey,
  planSnapshotKey,
  planPublishedKey,
  behaviorHistoryKey,
  suggestionFeedbackKey,
  personalizationEnabledKey,
  shownReminderKey,
  reminderSettingsSnapshotKey,
];

function clearLocalUserCache() {
  personalCacheKeys.forEach((key) => localStorage.removeItem(key));
}

function setAuthView(view) {
  activeAuthView = view;
  authTabs.hidden = false;
  const registering = view === "register";
  authViewButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.authView === view);
  });
  accessTitle.textContent = registering
    ? "创建易程智策账号"
    : "登录易程智策";
  accessDescription.textContent = registering
    ? "创建一次，手机和电脑登录后自动同步同一份个人数据。"
    : "手机和电脑登录同一账号，课表、偏好、对话和日程自动同步。";
  loginDisplayNameField.hidden = !registering;
  loginPasswordConfirmField.hidden = !registering;
  loginPasswordConfirm.required = registering;
  loginPassword.autocomplete = registering ? "new-password" : "current-password";
  loginUsernameLabel.textContent = "账号";
  loginSubmit.textContent = registering ? "创建并登录" : "登录";
  loginUsername.value = "";
  loginPassword.value = "";
  loginPasswordConfirm.value = "";
  loginMessage.textContent = registering
    ? "账号可使用学号、邮箱或自定义名称；密码至少 8 位。"
    : "还没有账号可以直接创建。";
}

function setBootstrapView() {
  activeAuthView = "bootstrap";
  authTabs.hidden = true;
  accessTitle.textContent = "进入易程智策";
  accessDescription.textContent = "请先输入产品统一入口账号和密码。";
  loginDisplayNameField.hidden = true;
  loginPasswordConfirmField.hidden = true;
  loginPasswordConfirm.required = false;
  loginUsernameLabel.textContent = "产品账号";
  loginUsername.value = productEntryUsername;
  loginPassword.value = "";
  loginPassword.autocomplete = "current-password";
  loginSubmit.textContent = "继续";
  loginMessage.textContent = "验证后可登录个人账号，或直接进入共享测试空间。";
}

authViewButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    if (button.dataset.authView !== "test") {
      setAuthView(button.dataset.authView);
      return;
    }
    button.disabled = true;
    loginMessage.textContent = "正在进入共享测试空间…";
    try {
      const response = await fetch("/api/v1/auth/test-session", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw data;
      const previousUserId = localStorage.getItem("yicheng_user_id");
      if (previousUserId !== data.user_id) clearLocalUserCache();
      localStorage.setItem(accessTokenKey, data.access_token);
      localStorage.setItem(sessionModeKey, data.session_mode);
      localStorage.setItem("yicheng_user_id", data.user_id);
      globalThis.location.reload();
    } catch (error) {
      loginMessage.textContent = error?.error?.message || "测试空间暂时无法进入，请稍后重试。";
      button.disabled = false;
    }
  });
});

async function initializeAccess() {
  try {
    const response = await fetch("/api/v1/auth/status");
    const status = await response.json();
    if (!status.enabled) {
      activeAccessMode = "local";
      accessGate.hidden = true;
      logoutButton.hidden = true;
      return true;
    }
    productEntryUsername = status.test_username || "";
    if (status.authenticated && ["test", "normal"].includes(status.session_mode)) {
      activeAccessMode = status.session_mode;
      const previousUserId = localStorage.getItem("yicheng_user_id");
      if (previousUserId && previousUserId !== status.user_id) clearLocalUserCache();
      consoleUserId = status.user_id;
      localStorage.setItem("yicheng_user_id", status.user_id);
      localStorage.setItem(sessionModeKey, activeAccessMode);
      if (!localStorage.getItem("yicheng_thread_id")) {
        consoleThreadId = getOrCreateLocalIdentity("yicheng_thread_id", "thread");
      }
      accessGate.hidden = true;
      logoutButton.hidden = false;
      logoutButton.textContent = status.account_name
        ? `${status.account_name} · 退出`
        : "退出";
      return true;
    }
    if (status.authenticated && status.session_mode === "bootstrap") {
      activeAccessMode = "bootstrap";
      localStorage.setItem(sessionModeKey, "bootstrap");
      setAuthView("login");
      accessGate.hidden = false;
      logoutButton.hidden = true;
      return false;
    }
    localStorage.removeItem(accessTokenKey);
    localStorage.removeItem(sessionModeKey);
    setBootstrapView();
    accessGate.hidden = false;
    logoutButton.hidden = true;
    return false;
  } catch {
    accessGate.hidden = false;
    loginMessage.textContent = "暂时无法检查登录状态，请稍后刷新页面。";
    return false;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (activeAuthView === "register" && loginPassword.value !== loginPasswordConfirm.value) {
    loginMessage.textContent = "两次输入的密码不一致。";
    return;
  }
  loginSubmit.disabled = true;
  loginMessage.textContent = activeAuthView === "bootstrap"
    ? "正在验证产品入口…"
    : activeAuthView === "register" ? "正在创建账号…" : "正在登录…";
  const endpoint = activeAuthView === "bootstrap"
    ? "/api/v1/auth/login"
    : activeAuthView === "register"
      ? "/api/v1/auth/register"
      : "/api/v1/auth/account/login";
  const payload = {
    username: loginUsername.value.trim(),
    password: loginPassword.value,
  };
  if (activeAuthView === "register") payload.display_name = loginDisplayName.value.trim() || null;
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw data;
    const previousUserId = localStorage.getItem("yicheng_user_id");
    if (data.user_id && previousUserId && previousUserId !== data.user_id) clearLocalUserCache();
    localStorage.setItem(accessTokenKey, data.access_token);
    localStorage.setItem(sessionModeKey, data.session_mode);
    if (data.user_id) localStorage.setItem("yicheng_user_id", data.user_id);
    globalThis.location.reload();
  } catch (error) {
    loginMessage.textContent = error?.error?.message || "登录没有成功，请稍后重试。";
    loginSubmit.disabled = false;
  }
});

logoutButton.addEventListener("click", () => {
  localStorage.removeItem(accessTokenKey);
  localStorage.removeItem(sessionModeKey);
  localStorage.removeItem("yicheng_user_id");
  clearLocalUserCache();
  globalThis.location.reload();
});

function configureSessionWorkspace() {
  const mode = activeAccessMode || localStorage.getItem(sessionModeKey);
  return { mode, onboarding: false };
}

const sourceLabels = {
  user: "用户提供",
  live_api: "实时数据",
  structured: "结构化规则",
  demo_fixture: "演示数据",
  cache: "缓存数据",
  estimated: "估算数据",
  rag: "知识检索",
  unknown: "暂不可用",
};

const memoryDefinitions = {
  buffer_min: {
    label: "日程缓冲时间",
    placeholder: "例如：15分钟",
    category: "preference",
  },
  walking_speed: {
    label: "步行节奏",
    placeholder: "慢、正常或快",
    category: "preference",
  },
  transport_mode: {
    label: "常用出行方式",
    placeholder: "步行、自行车或电瓶车",
    category: "preference",
  },
  avoid_congestion: {
    label: "偏好错峰通勤",
    placeholder: "是或否",
    category: "preference",
  },
  schedule_pace: {
    label: "日程节奏",
    placeholder: "宽松、适中或紧凑",
    category: "preference",
  },
  activity_location: {
    label: "事项地点偏好",
    placeholder: "例如：跑步 → 东操场；自习 → 图书馆12层",
    category: "preference",
  },
  preferred_study_period: {
    label: "高效学习时段",
    placeholder: "上午、下午或晚上",
    category: "habit",
  },
  preferred_study_location: {
    label: "自习地点（快捷设置）",
    placeholder: "例如：图书馆12层",
    category: "preference",
  },
  usual_lunch_time: {
    label: "常用午餐时间",
    placeholder: "例如：12:25",
    category: "habit",
  },
  usual_dinner_time: {
    label: "常用晚餐时间",
    placeholder: "例如：18:00",
    category: "habit",
  },
  usual_bedtime: {
    label: "常用就寝时间",
    placeholder: "例如：23:30",
    category: "habit",
  },
  usual_wake_time: {
    label: "常用起床时间",
    placeholder: "例如：07:00",
    category: "habit",
  },
  sleep_goal_hours: {
    label: "希望睡眠时长",
    placeholder: "例如：7.5小时",
    category: "preference",
  },
};
const retiredMemoryKeys = new Set([
  "avoid_rain",
  "avoid_tight_schedule",
  "preferred_locations",
  "weekly_daily_focus_limit_min",
]);

function behaviorTopic(title) {
  const definitions = [
    ["study", "自习", ["自习", "学习", "复习", "阅读"]],
    ["exercise", "运动", ["跑步", "运动", "健身", "锻炼"]],
    ["meal", "用餐", ["吃饭", "用餐", "早餐", "午餐", "晚餐"]],
    ["parcel", "取快递", ["快递", "取件", "驿站"]],
  ];
  return definitions.find(([, , markers]) =>
    markers.some((marker) => title.includes(marker))
  ) || null;
}

function roundedHalfHour(value) {
  const [hour, minute] = value.split(":").map(Number);
  const total = Math.round((hour * 60 + minute) / 30) * 30;
  const normalized = Math.min(total, 23 * 60 + 30);
  return `${String(Math.floor(normalized / 60)).padStart(2, "0")}:${
    String(normalized % 60).padStart(2, "0")
  }`;
}

function median(values) {
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.floor(ordered.length / 2)];
}

function recordBehaviorHistory(data) {
  if (!data.current_plan_saved || data.plan?.status !== "valid") return;
  const existing = readLocalSnapshot(behaviorHistoryKey, [])
    .filter((item) => item.plan_id !== data.plan.id);
  const campusId = currentCampusProfile?.campus_id || null;
  const additions = (data.plan.items || [])
    .filter((item) => item.item_type === "task")
    .flatMap((item) => {
      const topic = behaviorTopic(item.title || "");
      if (!topic || item.reason === "固定或用户锁定任务") return [];
      const [, taskTitle] = topic;
      const start = timePart(item.start_at);
      return [{
        plan_id: data.plan.id,
        date: data.plan.date,
        campus_id: campusId,
        topic: topic[0],
        task_title: taskTitle,
        start_time: start,
        duration_min: Math.max(
          5,
          Math.round(
            (new Date(item.end_at) - new Date(item.start_at)) / 60000,
          ),
        ),
        location_name: item.location_id
          ? data.location_names?.[item.location_id] || null
          : null,
      }];
    });
  writeLocalSnapshot(
    behaviorHistoryKey,
    [...additions, ...existing].slice(0, 80),
  );
  renderPersonalizationState();
}

function buildBehaviorPatterns() {
  const history = readLocalSnapshot(behaviorHistoryKey, []);
  const feedback = readLocalSnapshot(suggestionFeedbackKey, {});
  const groups = new Map();
  history.forEach((item) => {
    if (
      currentCampusProfile?.campus_id
      && item.campus_id
      && item.campus_id !== currentCampusProfile.campus_id
    ) return;
    const timeBucket = roundedHalfHour(item.start_time);
    const key = [
      item.campus_id || "current",
      item.topic,
      timeBucket,
      item.location_name || "",
    ].join("|");
    if (!groups.has(key)) groups.set(key, new Map());
    groups.get(key).set(item.date, { ...item, time_bucket: timeBucket });
  });
  return [...groups.entries()]
    .map(([key, byDate]) => {
      const values = [...byDate.values()];
      const response = feedback[`habit:${key}`] || {};
      return {
        key,
        task_title: values[0]?.task_title,
        typical_start: values[0]?.time_bucket,
        duration_min: median(values.map((item) => item.duration_min)),
        location_name: values[0]?.location_name || null,
        campus_id: values[0]?.campus_id || null,
        occurrences: values.length,
        dismissed_count: response.dismissed_count || 0,
        last_dismissed_at: response.last_dismissed_at || null,
        last_suggested_at: response.last_suggested_at || null,
      };
    })
    .filter((item) => item.occurrences >= 3)
    .sort((left, right) => right.occurrences - left.occurrences)
    .slice(0, 20);
}

function personalizationSnapshot() {
  const enabled = localStorage.getItem(personalizationEnabledKey) === "true";
  return {
    enabled,
    behavior_patterns: enabled ? buildBehaviorPatterns() : [],
  };
}

function renderPersonalizationState() {
  const enabled = localStorage.getItem(personalizationEnabledKey) === "true";
  const patterns = buildBehaviorPatterns();
  personalizationToggle.checked = enabled;
  personalizationReset.hidden = patterns.length === 0;
  personalizationState.textContent = enabled
    ? patterns.length
      ? `已开启，发现 ${patterns.length} 个稳定习惯；只询问，不会自动加入。`
      : "已开启；同类行为在不同日期出现至少3次后，才会形成建议。"
    : "当前关闭。历史仍保存在本机，开启后才会用于生成建议。";
}

personalizationToggle.addEventListener("change", () => {
  localStorage.setItem(
    personalizationEnabledKey,
    String(personalizationToggle.checked),
  );
  renderPersonalizationState();
});

personalizationReset.addEventListener("click", () => {
  localStorage.removeItem(suggestionFeedbackKey);
  renderPersonalizationState();
  personalizationState.textContent = (
    "建议降频记录已重置；已识别的行为历史仍保留在本机。"
  );
});

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function timePart(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
}

function formatDuration(minutes) {
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  const hours = Math.floor(total / 60);
  const remainder = total % 60;
  const parts = [];
  if (hours) parts.push(`${hours}小时`);
  if (remainder || !parts.length) parts.push(`${remainder}分钟`);
  return parts.join("");
}

function renderClock() {
  if (serverClockBaseMs === null || serverClockFetchedAtMs === null) return;
  const current = new Date(
    serverClockBaseMs + (Date.now() - serverClockFetchedAtMs),
  );
  const formatted = new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(current);
  clock.textContent = `北京时间 ${formatted}`;
}

function renderTimeline(data) {
  const items = [...(data.plan?.items || [])].filter(
    (item) => item.item_type !== "meal",
  ).sort(
    (left, right) => (
      new Date(left.start_at).getTime() - new Date(right.start_at).getTime()
      || new Date(left.end_at).getTime() - new Date(right.end_at).getTime()
    ),
  );
  const locationNames = data.location_names || {};
  const hiddenMealTaskIds = new Set([
    ...(data.plan?.items || []),
    ...(data.previous_plan?.items || []),
  ].filter((item) => item.item_type === "meal").map((item) => item.task_id));
  const changes = (data.plan_diff || []).filter(
    (change) => !hiddenMealTaskIds.has(change.task_id),
  );
  const changesByTask = new Map(
    changes.map((change) => [change.task_id, change]),
  );
  if (resultChangeSummary) {
    const hasPreviousPlan = Boolean(data.previous_plan);
    const previousTravel = data.previous_plan?.metrics?.travel_minutes || 0;
    const currentTravel = data.plan?.metrics?.travel_minutes || 0;
    const travelDelta = hasPreviousPlan
      ? currentTravel - previousTravel
      : 0;
    const waitingDelta = hasPreviousPlan
      ? planIdleMinutes(data.plan) - planIdleMinutes(data.previous_plan)
      : 0;
    const changeCards = changes.map((change) => {
      const before = change.before_start
        ? `${timePart(change.before_start)}—${timePart(change.before_end)}`
        : "未安排";
      const after = change.after_start
        ? `${timePart(change.after_start)}—${timePart(change.after_end)}`
        : "已移除";
      return `<span class="result-change-chip ${escapeHtml(change.change_type)}">
        <b>${escapeHtml(change.title)}</b>
        <em>${escapeHtml(change.summary)}</em>
        <small>${before} → ${after}</small>
      </span>`;
    });
    if (travelDelta) {
      changeCards.push(`<span class="result-change-chip travel-change">
        <b>通勤时间</b>
        <em>${travelDelta < 0 ? "减少" : "增加"}${formatDuration(Math.abs(travelDelta))}</em>
        <small>${formatDuration(previousTravel)} → ${formatDuration(currentTravel)}</small>
      </span>`);
    }
    if (waitingDelta) {
      const previousWaiting = planIdleMinutes(data.previous_plan);
      const currentWaiting = planIdleMinutes(data.plan);
      changeCards.push(`<span class="result-change-chip waiting-change">
        <b>等待空档</b>
        <em>${waitingDelta < 0 ? "减少" : "增加"}${formatDuration(Math.abs(waitingDelta))}</em>
        <small>${formatDuration(previousWaiting)} → ${formatDuration(currentWaiting)}</small>
      </span>`);
    }
    resultChangeSummary.innerHTML = changeCards.length
      ? `<strong>本次调整</strong><div>${changeCards.join("")}</div>`
      : "";
    resultChangeSummary.hidden = changeCards.length === 0;
  }
  const pendingCount = (data.task_statuses || [])
    .filter((task) => task.status === "needs_adjustment").length;
  planTitle.textContent = pendingCount
    ? "当前可安排部分"
    : "完整日程时间轴";
  timeline.classList.toggle("empty", items.length === 0);
  timeline.innerHTML = items.length
    ? items.map((item) => {
      const isTravel = item.item_type === "travel";
      const travelModeLabels = {
        walk: "步行通勤",
        bicycle: "自行车通勤",
        electrobike: "电瓶车通勤",
      };
      const title = isTravel
        ? travelModeLabels[item.travel_mode] || "通勤"
        : item.title;
      const location = item.location_raw || (item.location_id
        ? locationNames[item.location_id] || "地点待确认"
        : "地点未设置");
      const reason = isTravel
        ? item.congestion_delay_min > 0
          ? "高峰拥挤"
          : ""
        : "";
      const itemIcon = isTravel
        ? "travel"
        : title.includes("图书馆") || title.includes("学习") || title.includes("自习")
          ? "book"
          : title.includes("快递") || title.includes("报名")
            ? "package"
            : title.includes("跑步") || title.includes("运动")
              ? "activity"
               : "calendar";
      const change = isTravel ? null : changesByTask.get(item.task_id);
      return `
        <div class="timeline-item ${isTravel ? "travel" : ""} ${isTravel && item.congestion_delay_min > 0 ? "congested" : ""} ${change ? `has-change ${escapeHtml(change.change_type)}` : ""}">
          <div class="time">${timePart(item.start_at)}—${timePart(item.end_at)}</div>
          <div class="rail"><span></span></div>
          <div class="content">
            <span class="timeline-kind-icon">${dashboardIcon(itemIcon)}</span>
            <strong>${escapeHtml(title)}</strong>
            ${change ? `<span class="timeline-change-badge">${escapeHtml(change.summary)}</span>` : ""}
            ${location ? `<small>${escapeHtml(location)}</small>` : ""}
            ${change?.before_start ? `<small class="timeline-before-time">原计划 ${timePart(change.before_start)}—${timePart(change.before_end)}</small>` : ""}
            ${reason ? `<p>${escapeHtml(reason)}</p>` : ""}
          </div>
        </div>`;
    }).join("")
    : "没有生成结构化日程。";
}

function setResultMode(active) {
  const wasActive = document.body.classList.contains("has-plan-result");
  document.body.classList.toggle("has-plan-result", active);
  setActiveWorkspaceView(activeWorkspaceView);
  if (!active) return;
  if (activeWorkspaceView !== "chat") setActiveWorkspaceView("chat");
  if (wasActive) return;
  requestAnimationFrame(() => {
    globalThis.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function setInlineRequestEditing(active) {
  resultRequest.classList.toggle("is-editing", active);
  resultRequestText.hidden = active;
  resultRequestInput.hidden = !active;
  resultEdit.textContent = active ? "取消修改" : "修改需求";
  resultRerun.textContent = active ? "按新需求规划" : "重新规划";
  if (active) {
    resultRequestInput.value = lastResultQuery;
    resultRequestInput.focus();
    resultRequestInput.setSelectionRange(
      resultRequestInput.value.length,
      resultRequestInput.value.length,
    );
  }
}

function renderResultSummary(data) {
  const plan = data.plan;
  if (!plan) {
    resultSummary.innerHTML = "";
    resultSummary.hidden = true;
    return;
  }
  const metrics = plan.metrics || {};
  const statuses = data.task_statuses || [];
  const scheduled = statuses.length
    ? statuses.filter((item) => item.status === "scheduled").length
    : metrics.scheduled_task_count || 0;
  const requested = statuses.length || metrics.requested_task_count || 0;
  const checks = data.constraint_checks || [];
  const passed = checks.filter((item) => item.passed).length;
  const endTimes = (plan.items || []).filter(
    (item) => item.item_type !== "meal",
  ).map((item) => new Date(item.end_at).getTime());
  const finalEnd = endTimes.length
    ? timePart(new Date(Math.max(...endTimes)))
    : "—";
  const feasible = plan.status === "valid" && scheduled === requested;
  const cards = [
    [
      feasible ? "可执行" : "需调整",
      feasible ? "所有任务均已安排" : "有任务需要调整",
      feasible ? "success" : "attention",
      "feasibility",
    ],
    [
      `${scheduled}/${requested}`,
      "任务已安排",
      scheduled === requested ? "success" : "attention",
      "tasks",
    ],
    [finalEnd, "预计结束时间", "time", "end"],
    [formatDuration(metrics.buffer_minutes || 0), "弹性缓冲", "time", "buffer"],
    [formatDuration(metrics.travel_minutes || 0), "校园通勤", "time", "travel"],
    [
      `${passed}/${checks.length}`,
      "约束检查通过",
      passed === checks.length ? "success" : "attention",
      "checks",
    ],
  ];
  resultSummary.hidden = false;
  resultSummary.innerHTML = cards.map(([value, label, state, kind]) => `
    <div class="result-summary-card ${state}" data-kind="${kind}">
      <span class="result-summary-icon">${dashboardIcon(kind)}</span>
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
    </div>
  `).join("");
}

function renderResultDashboard(data) {
  if (!data.plan) {
    resultRequest.hidden = true;
    resultDetails.hidden = true;
    return;
  }
  const query = lastResultQuery || activeConversationQuery || "本次校园日程规划";
  resultRequestText.textContent = query;
  setInlineRequestEditing(false);
  resultRequest.hidden = false;

  const checks = data.constraint_checks || [];
  const passed = checks.filter((item) => item.passed).length;
  resultConstraintTotal.textContent = `${passed}/${checks.length} 通过`;
  resultConstraints.innerHTML = checks.length
    ? checks.map((check) => `
      <div class="result-check-item ${check.passed ? "passed" : "failed"}">
        <span>${check.passed ? dashboardIcon("feasibility") : "!"}</span>
        <div>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.message)}</small>
        </div>
        <em>${check.passed ? "通过" : "注意"}</em>
      </div>
    `).join("")
    : '<p class="result-detail-empty">暂无约束检查。</p>';

  const freshness = data.data_freshness || {};
  const isLive = (value) => value === "live_api";
  const sourceEntries = [
    {
      icon: "map",
      name: "高德地图",
      purpose: isLive(freshness.route)
        ? "实时路线与通勤计算"
        : "已接入 · 当前使用校准路线",
      state: isLive(freshness.route) ? "实时" : "演示",
    },
    {
      icon: "building",
      name: "场馆规则",
      purpose: "校园开放时间校验",
      state: "规则库",
    },
    {
      icon: "cloud",
      name: "高德天气",
      purpose: isLive(freshness.weather)
        ? "实时天气与降雨风险"
        : "冻结天气场景校验",
      state: isLive(freshness.weather) ? "实时" : "演示",
    },
    {
      icon: "calendar",
      name: "个人课表",
      purpose: "课程与空闲时间确认",
      state: "个人数据",
    },
  ];
  resultSources.innerHTML = sourceEntries.map((entry) => {
    return `
      <div class="result-source-item">
        <span class="result-source-icon">${dashboardIcon(entry.icon)}</span>
        <div><strong>${escapeHtml(entry.name)}</strong><small>${escapeHtml(entry.purpose)}</small></div>
        <em>${escapeHtml(entry.state)}</em>
      </div>`;
  }).join("");
  resultDetails.hidden = false;
}

function renderTaskStatuses(statuses = [], locationNames = {}) {
  if (!statuses.length) {
    taskStatuses.innerHTML = "";
    return;
  }
  const scheduledCount = statuses
    .filter((task) => task.status === "scheduled").length;
  const pendingCount = statuses.length - scheduledCount;
  taskStatuses.innerHTML = `
    <div class="task-status-summary">
      <strong>任务完整性</strong>
      <span>已安排 ${scheduledCount}/${statuses.length}${
        pendingCount ? ` · ${pendingCount}项待调整` : ""
      }</span>
    </div>
    ${statuses.map((task) => {
      const pending = task.status === "needs_adjustment";
      const location = task.location_id
        ? ` · ${escapeHtml(
          locationNames[task.location_id] || "地点待确认"
        )}`
        : "";
      return `
        <div class="task-status-item ${
          pending ? "needs-adjustment" : "scheduled"
        }">
          <span class="task-status-icon">${pending ? "!" : "✓"}</span>
          <div>
            <strong>${escapeHtml(task.title)}</strong>
            <small>${task.duration_min}分钟${location} · ${
              escapeHtml(task.message)
            }</small>
          </div>
          <span class="task-status-badge">${
            pending ? "待调整" : "已安排"
          }</span>
        </div>`;
    }).join("")}
  `;
}

function renderExecution(steps = []) {
  execution.classList.toggle("empty", steps.length === 0);
  execution.innerHTML = steps.length
    ? steps.map((step, index) => `
      <div class="execution-item ${escapeHtml(step.status)}">
        <span class="execution-index">${index + 1}</span>
        <div>
          <strong>${escapeHtml(step.label)}</strong>
          <small>${escapeHtml(step.detail)}</small>
        </div>
        <span class="execution-state">${
          step.status === "success" ? "完成"
            : step.status === "fallback" ? "降级完成"
              : step.status === "failed" ? "未通过" : "等待"
        }</span>
      </div>`).join("")
    : "运行后显示五个处理步骤。";
}

function renderConstraints(checks = []) {
  constraints.classList.toggle("empty", checks.length === 0);
  constraints.innerHTML = checks.length
    ? checks.map((check) => `
      <div class="check-item ${check.passed ? "passed" : "failed"}">
        <span class="check-icon">${check.passed ? "✓" : "!"}</span>
        <div>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.message)}</small>
        </div>
      </div>`).join("")
    : "生成后显示检查结果。";
}

function renderDiff(data) {
  const changes = data.plan_diff || [];
  const hasChanges = changes.length > 0 || Boolean(data.adjustment_reason);
  adjustmentPanel.classList.toggle("has-changes", hasChanges);
  adjustment.textContent = data.adjustment_reason || "当前没有计划变更。";
  adjustment.classList.toggle("muted", !data.adjustment_reason);
  diff.innerHTML = changes.map((change) => `
    <div class="diff-item">
      <div>
        <strong>${escapeHtml(change.title)}</strong>
        <span>${escapeHtml(change.summary)}</span>
      </div>
      <small>
        ${change.before_start ? `${timePart(change.before_start)}—${timePart(change.before_end)}` : "未安排"}
        <b>→</b>
        ${change.after_start ? `${timePart(change.after_start)}—${timePart(change.after_end)}` : "已移除"}
      </small>
    </div>`).join("");
}

function renderEvidence(data) {
  const sourceEntries = Object.entries(data.data_freshness || {});
  const sourceNames = { route: "路径", weather: "天气", knowledge: "知识" };
  freshness.innerHTML = sourceEntries.map(([key, value]) => `
    <span class="tag">${sourceNames[key] || key} · ${sourceLabels[value] || value}</span>
  `).join("");

  const hiddenTechnicalCodes = new Set([
    "API_DEGRADED",
    "UNVERIFIED_CAMPUS_DATA",
    "PARTIAL_LIVE_ROUTE_COVERAGE",
    "ROUTE_FALLBACK",
    "LLM_DEGRADED",
  ]);
  const warningItems = (data.warnings || []).filter(
    (item) => (
      !hiddenTechnicalCodes.has(item.code)
      || (
        item.code === "ROUTE_FALLBACK"
        && item.message?.includes("电瓶车实时路线")
      )
    ),
  );
  const careInsights = (data.insights || []).filter(
    (item) => ["required", "attention"].includes(item.importance)
      && !["规划时间基准", "通勤方式与高峰缓冲"].includes(item.title),
  );
  const careItems = [
    ...warningItems.map((item) => ({
      title: item.severity === "error" ? "需处理" : "数据说明",
      message: item.message,
      error: item.severity === "error",
    })),
    ...careInsights.map((item) => ({
      title: item.title,
      message: item.content,
      error: false,
    })),
  ].filter((item, index, items) => (
    items.findIndex((candidate) => candidate.message === item.message) === index
  )).slice(0, 4);
  warnings.classList.toggle("muted", careItems.length === 0);
  warnings.innerHTML = careItems.length
    ? careItems.map((item) => `
      <div class="warning ${item.error ? "error" : ""}">
        <strong>${escapeHtml(item.title)}</strong>
        <span>${escapeHtml(item.message)}</span>
      </div>`).join("")
    : "暂时没有提醒。";
}

function renderInsights(items = []) {
  insights.classList.toggle("empty", items.length === 0);
  insights.innerHTML = items.length
    ? items.map((item) => `
      <div class="insight-item ${escapeHtml(item.importance)}">
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml(item.source_label)}</small>
        </div>
        <p>${escapeHtml(item.content)}</p>
      </div>
    `).join("")
    : "本次没有需要额外展示的依据。";
}

function renderDebug(payload) {
  lastDebugPayload = payload;
  debugContent.textContent = payload
    ? JSON.stringify(payload, null, 2)
    : "尚无运行数据。";
}

function renderSuggestedActions(actions = []) {
  lastSuggestedActions = actions;
  const feedback = readLocalSnapshot(suggestionFeedbackKey, {});
  actions
    .filter((action) => action.kind === "habit_suggestion")
    .forEach((action) => {
      feedback[action.id] = {
        ...(feedback[action.id] || {}),
        last_suggested_at: new Date().toISOString(),
      };
    });
  writeLocalSnapshot(suggestionFeedbackKey, feedback);
  assistantActions.innerHTML = actions.map((action, index) => `
    <div class="suggestion-card ${
      action.kind === "habit_suggestion" ? "habit" : ""
    }">
      <button class="suggestion-button" data-action-index="${index}">
        <strong>${escapeHtml(action.label)}</strong>
        <span>${escapeHtml(action.description)}</span>
      </button>
      ${action.dismissible ? `
        <button class="suggestion-dismiss" data-dismiss-index="${index}">
          这次不用
        </button>
      ` : ""}
    </div>
  `).join("");
  assistantActions.querySelectorAll("[data-action-index]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = lastSuggestedActions[
        Number(button.dataset.actionIndex)
      ];
      if (!action) return;
      queryInput.value = action.query;
      await submitQuery(action.query);
    });
  });
  assistantActions.querySelectorAll("[data-dismiss-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = lastSuggestedActions[
        Number(button.dataset.dismissIndex)
      ];
      if (!action) return;
      const current = readLocalSnapshot(suggestionFeedbackKey, {});
      const item = current[action.id] || {};
      current[action.id] = {
        ...item,
        dismissed_count: (item.dismissed_count || 0) + 1,
        last_dismissed_at: new Date().toISOString(),
      };
      writeLocalSnapshot(suggestionFeedbackKey, current);
      button.closest(".suggestion-card")?.remove();
      renderPersonalizationState();
    });
  });
}

function renderPlanPanels(data) {
  renderTimeline(data);
  renderResultSummary(data);
  renderResultDashboard(data);
  renderTaskStatuses(data.task_statuses, data.location_names);
  renderExecution(data.execution_steps);
  renderConstraints(data.constraint_checks);
  renderDiff(data);
  renderEvidence(data);
  renderInsights(data.insights || []);
}

function renderResponse(data) {
  const shouldStayInDashboard = document.body.classList.contains(
    "has-plan-result",
  );
  lastResultData = data;
  pendingPlanCandidate = null;
  if (resultCandidateActions) {
    resultCandidateActions.hidden = true;
    resultCandidateActions.querySelectorAll("button").forEach((item) => {
      item.disabled = false;
    });
  }
  if (resultActionStatus) resultActionStatus.hidden = true;
  if (data.current_plan_saved && data.plan?.status === "valid") {
    writeLocalSnapshot(planSnapshotKey, data.plan);
  }
  recordBehaviorHistory(data);
  answer.textContent = data.answer;
  answer.classList.remove("muted");
  completeConversationTurn(data.answer);
  const planPublished = Boolean(
    data.plan?.id
    && localStorage.getItem(planPublishedKey) === data.plan.id
  );
  if (data.current_plan_saved && data.plan?.status === "valid") {
    const dateLabel = `${data.plan.date.slice(5, 7).replace(/^0/, "")}月${data.plan.date.slice(8, 10).replace(/^0/, "")}日`;
    saveState.textContent = planPublished
      ? `已加入 ${dateLabel} 日程`
      : "方案已自动保存";
    if (resultAddAgenda) {
      resultAddAgenda.hidden = false;
      resultAddAgenda.disabled = false;
      resultAddAgenda.textContent = planPublished ? "查看日程" : "加入日程";
    }
  } else {
    saveState.textContent = data.plan
      ? "结果未写入当前计划"
      : "尚未生成当前计划";
    if (resultAddAgenda) resultAddAgenda.hidden = true;
  }
  saveState.classList.toggle("saved", planPublished);
  renderPlanPanels(data);
  renderSuggestedActions(data.suggested_actions);
  renderDebug(data);
  if (data.plan) {
    setResultMode(true);
  } else if (shouldStayInDashboard) {
    resultRequestText.textContent = lastResultQuery;
    setInlineRequestEditing(false);
    resultRequest.hidden = false;
    resultDetails.hidden = true;
    planTitle.textContent = "需要补充信息";
    timeline.className = "timeline empty";
    timeline.textContent = data.answer || "请补充需求后重新规划。";
    setResultMode(true);
  }
  if (data.current_plan_saved) {
    loadAgenda(agendaDate.value || shanghaiDateString()).catch((error) =>
      renderDebug(error),
    );
  }
}

function shanghaiDateString(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const fields = Object.fromEntries(
    parts.filter((item) => item.type !== "literal")
      .map((item) => [item.type, item.value]),
  );
  return `${fields.year}-${fields.month}-${fields.day}`;
}

const agendaSourceLabels = {
  course: "个人课表",
  plan: "对话安排",
  weekly: "周目标",
  manual: "手动添加",
};

function agendaItemDate(item) {
  return shanghaiDateString(new Date(item.start_at));
}

function renderAgenda(data, selectedDate) {
  const items = (data.items || []).filter(
    (item) => item.kind !== "meal" && agendaItemDate(item) === selectedDate,
  );
  const minutes = (item) => Math.max(
    0,
    Math.round((new Date(item.end_at) - new Date(item.start_at)) / 60000),
  );
  const dayBusy = items
    .filter((item) => item.kind !== "travel")
    .reduce((sum, item) => sum + minutes(item), 0);
  const courseCount = items.filter((item) => item.kind === "course").length;
  const dayReminders = (data.reminders || []).filter(
    (item) => shanghaiDateString(new Date(item.event_start_at)) === selectedDate,
  ).sort((left, right) =>
    new Date(left.notify_at).getTime() - new Date(right.notify_at).getTime()
  );
  const reminderCount = dayReminders.length;
  const today = shanghaiDateString();
  agendaState.textContent = selectedDate === today
    ? `今天 · ${items.length}项`
    : `${selectedDate.slice(5).replace("-", "月")}日 · ${items.length}项`;
  agendaState.classList.toggle("ready", items.length > 0);
  agendaMetrics.innerHTML = `
    <span>课程 ${courseCount} 节次段</span>
    <span>已安排 ${Math.round(dayBusy / 6) / 10} 小时</span>
    <span>提醒 ${reminderCount} 次</span>
    <span>已汇总未来7天</span>
  `;
  agendaList.classList.toggle("muted", items.length === 0);
  agendaList.innerHTML = items.length
    ? items.map((item) => `
      <div class="agenda-item ${escapeHtml(item.kind)}">
        <time>${escapeHtml(timePart(item.start_at))}
          —${escapeHtml(timePart(item.end_at))}</time>
        <span class="agenda-kind" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${item.location_name
            ? escapeHtml(item.location_name)
            : item.kind === "travel"
              ? "已预留通勤时间"
              : "地点未设置"}${
            item.locked ? " · 固定安排" : ""
          }</small>
        </div>
        <span class="agenda-source">${
          agendaSourceLabels[item.source] || "个人日程"
        }</span>
      </div>
    `).join("")
    : `
      <div class="weekly-safe">
        <strong>这一天还没有固定安排</strong>
        <span>可以通过上方对话告诉我想完成什么，也可以把它留给休息和临时变化。</span>
      </div>
    `;
  agendaReminders.innerHTML = dayReminders.length
    ? `
      <div class="agenda-reminder-heading">
        <strong>今天会这样提醒你</strong>
        <span>按时间先后排列，可在下方修改提前量</span>
      </div>
      <div class="agenda-reminder-list">
        ${dayReminders.slice(0, 6).map((item) => `
          <div class="agenda-reminder ${escapeHtml(item.kind)}">
            <time>${escapeHtml(timePart(item.notify_at))}</time>
            <div>
              <strong>${escapeHtml(item.title)}</strong>
              <span>${escapeHtml(item.body)}</span>
            </div>
          </div>
        `).join("")}
      </div>
    `
    : "";
  const careItems = data.care_suggestions || [];
  careSuggestions.innerHTML = careItems.length
    ? `
      <div class="care-heading">
        <strong>未来7天的生活关照</strong>
        <span>只给建议，不会未经确认写入日程</span>
      </div>
      ${careItems.map((item, index) => `
      <div class="care-card ${escapeHtml(item.level)}">
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.content)}</p>
        ${item.action_query ? `
          <button class="ghost" data-care-action="${index}">
            让我帮你找合适时段
          </button>
        ` : ""}
      </div>
      `).join("")}
    `
    : "";
  careSuggestions.querySelectorAll("[data-care-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const suggestion = data.care_suggestions[
        Number(button.dataset.careAction)
      ];
      if (!suggestion?.action_query) return;
      queryInput.value = suggestion.action_query;
      await submitQuery(suggestion.action_query);
    });
  });
}

async function loadAgendaRange(startDate, endDate) {
  const selectedDate = startDate;
  agendaDate.value = selectedDate;
  agendaState.textContent = "正在汇总";
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/agenda/contextual`
      + `?start_date=${encodeURIComponent(selectedDate)}`
      + `&end_date=${encodeURIComponent(endDate)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(personalContextPayload()),
    },
  );
  const data = await response.json();
  if (!response.ok) throw data;
  lastAgendaData = data;
  try {
    const calendarResponse = await fetch(
      `/api/v1/users/${consoleUserId}/calendar-context`
        + `?start_date=${encodeURIComponent(selectedDate)}`
        + `&end_date=${encodeURIComponent(endDate)}`,
    );
    const calendarData = await calendarResponse.json();
    if (!calendarResponse.ok) throw calendarData;
    scheduleCalendarContexts = Object.fromEntries(
      (calendarData.items || []).map((item) => [item.date, item]),
    );
  } catch (error) {
    scheduleCalendarContexts = {};
    renderDebug(error);
  }
  renderAgenda(data, selectedDate);
  if (!scheduleCursorDate) scheduleCursorDate = selectedDate;
  if (activeWorkspaceView === "schedule") renderScheduleViews();
  return data;
}

async function loadAgenda(selectedDate = shanghaiDateString()) {
  return loadAgendaRange(selectedDate, addWeeklyDays(selectedDate, 6));
}

function renderReminderSettings(payload) {
  const settings = payload.settings;
  currentReminderSettings = settings;
  writeLocalSnapshot(reminderSettingsSnapshotKey, settings);
  reminderCourse.value = settings.course_lead_min;
  reminderWakeup.value = settings.early_course_wakeup_min;
  reminderMeeting.value = settings.meeting_lead_min;
  reminderActivity.value = settings.activity_lead_min ?? 30;
  reminderStudy.value = settings.study_lead_min;
  reminderBedtime.value = settings.bedtime_lead_min;
  reminderBedtimeEnabled.checked = settings.bedtime_enabled !== false;
  const permission = "Notification" in globalThis
    ? Notification.permission
    : "unsupported";
  if (permission === "granted" && settings.browser_notifications) {
    reminderState.textContent = (
      "浏览器提醒已开启。网页打开时会自动检查；"
      + "需要关闭网页后仍提醒，请导出到系统日历。"
    );
    reminderEnable.textContent = "浏览器提醒已开启";
    reminderEnable.disabled = true;
    startReminderPolling();
  } else if (permission === "denied") {
    reminderState.textContent = (
      "浏览器已拒绝通知权限，可在浏览器网站设置中重新开启；"
      + "系统日历导出仍可使用。"
    );
    reminderEnable.textContent = "通知权限已被拒绝";
    reminderEnable.disabled = true;
  } else if (permission === "unsupported") {
    reminderState.textContent = (
      "当前浏览器不支持网页通知，可使用“导出到系统日历”。"
    );
    reminderEnable.disabled = true;
  } else {
    reminderState.textContent = (
      "浏览器提醒尚未开启；你的提前时间设置已经可以保存。"
    );
    reminderEnable.textContent = "开启浏览器提醒";
    reminderEnable.disabled = false;
  }
}

async function loadReminderSettings() {
  const saved = readLocalSnapshot(reminderSettingsSnapshotKey, null);
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/reminders/settings`,
    saved
      ? {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(saved),
        }
      : undefined,
  );
  const data = await response.json();
  if (!response.ok) throw data;
  renderReminderSettings(data);
}

function reminderPayload(overrides = {}) {
  return {
    enabled: true,
    browser_notifications:
      currentReminderSettings?.browser_notifications || false,
    bedtime_enabled: reminderBedtimeEnabled.checked,
    course_lead_min: Number(reminderCourse.value),
    early_course_wakeup_min: Number(reminderWakeup.value),
    meeting_lead_min: Number(reminderMeeting.value),
    activity_lead_min: Number(reminderActivity.value),
    study_lead_min: Number(reminderStudy.value),
    exercise_lead_min:
      currentReminderSettings?.exercise_lead_min ?? 15,
    task_lead_min: currentReminderSettings?.task_lead_min ?? 10,
    bedtime_lead_min: Number(reminderBedtime.value),
    quiet_start: currentReminderSettings?.quiet_start || "23:00:00",
    quiet_end: currentReminderSettings?.quiet_end || "06:30:00",
    ...overrides,
  };
}

async function saveReminderSettings(overrides = {}) {
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/reminders/settings`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reminderPayload(overrides)),
    },
  );
  const data = await response.json();
  if (!response.ok) throw data;
  renderReminderSettings(data);
  await loadAgenda(agendaDate.value || shanghaiDateString());
}

async function serviceWorkerRegistration() {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/sw.js");
}

async function showReminderNotification(item) {
  const registration = await serviceWorkerRegistration().catch(() => null);
  const options = {
    body: item.body,
    tag: item.id,
    renotify: false,
    data: { url: "/" },
  };
  if (registration) {
    await registration.showNotification(item.title, options);
  } else {
    new Notification(item.title, options);
  }
}

async function pollDueReminders() {
  if (
    !currentReminderSettings?.browser_notifications
    || !("Notification" in globalThis)
    || Notification.permission !== "granted"
  ) return;
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/reminders/due/contextual?window_min=2`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(personalContextPayload()),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    const shown = readLocalSnapshot(shownReminderKey, {});
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
    Object.entries(shown).forEach(([key, value]) => {
      if (new Date(value).getTime() < cutoff) delete shown[key];
    });
    for (const item of data.reminders || []) {
      if (shown[item.id]) continue;
      await showReminderNotification(item);
      shown[item.id] = new Date().toISOString();
    }
    writeLocalSnapshot(shownReminderKey, shown);
  } catch (error) {
    reminderState.textContent = (
      "这次自动检查提醒没有成功，我会稍后再试；"
      + "已导入系统日历的闹钟不受影响。"
    );
    renderDebug(error);
  }
}

function startReminderPolling() {
  if (reminderPollTimer !== null) return;
  pollDueReminders();
  reminderPollTimer = setInterval(pollDueReminders, 30000);
}

agendaToday.addEventListener("click", () => {
  scheduleCursorDate = shanghaiDateString();
  loadAgenda(scheduleCursorDate).catch((error) => renderDebug(error));
});

agendaRefresh.addEventListener("click", () => {
  loadAgenda(agendaDate.value || shanghaiDateString())
    .catch((error) => renderDebug(error));
});

agendaDate.addEventListener("change", () => {
  if (!agendaDate.value) return;
  scheduleCursorDate = agendaDate.value;
  loadAgenda(agendaDate.value).catch((error) => renderDebug(error));
});

reminderSave.addEventListener("click", async () => {
  reminderSave.disabled = true;
  try {
    await saveReminderSettings();
    reminderState.textContent = "提醒时间已经保存。";
  } catch (error) {
    reminderState.textContent = error?.error?.message
      || "提醒设置暂时没有保存成功。";
    renderDebug(error);
  } finally {
    reminderSave.disabled = false;
  }
});

reminderEnable.addEventListener("click", async () => {
  if (!("Notification" in globalThis)) return;
  const permission = await Notification.requestPermission();
  if (permission === "granted") {
    await serviceWorkerRegistration().catch(() => null);
    await saveReminderSettings({ browser_notifications: true });
    await pollDueReminders();
  } else {
    reminderState.textContent = (
      "没有获得通知权限。你仍可以导出到系统日历，用系统闹钟提醒。"
    );
  }
});

agendaExport.addEventListener("click", async (event) => {
  event.preventDefault();
  const startDate = agendaDate.value || shanghaiDateString();
  const endDate = addWeeklyDays(startDate, 90);
  agendaExport.textContent = "正在生成日历文件…";
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/agenda.ics/contextual`
        + `?start_date=${encodeURIComponent(startDate)}`
        + `&end_date=${encodeURIComponent(endDate)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(personalContextPayload()),
      },
    );
    if (!response.ok) throw await response.json();
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `易程智策个人日程_${startDate}.ics`;
    link.click();
    URL.revokeObjectURL(url);
    reminderState.textContent = (
      "日历文件已生成。导入手机或电脑日历后，系统会按提醒时间通知。"
    );
  } catch (error) {
    reminderState.textContent = error?.error?.message
      || "日历文件暂时没有生成成功。";
    renderDebug(error);
  } finally {
    agendaExport.textContent = "导出到系统日历（含闹钟）";
  }
});

function renderError(error) {
  const body = error?.error || {};
  answer.textContent = body.message || "请求失败，请稍后重试。";
  answer.classList.remove("muted");
  completeConversationTurn(answer.textContent);
  warnings.innerHTML = `
    <div class="warning error">
      <strong>请求未完成</strong>
      <span>请检查输入后重试；如果仍然失败，可展开页面底部调试信息。</span>
    </div>`;
  renderDebug(error);
}

function setLoading(active) {
  submitButton.disabled = active;
  resetButton.disabled = active;
  submitButton.textContent = active ? "正在认真规划…" : "发送给易程智策";
}

async function runRequest(
  url,
  options = {},
  transformData = null,
  { render = true } = {},
) {
  setLoading(true);
  try {
    const response = await fetch(url, options);
    let data = await response.json();
    if (!response.ok) throw data;
    if (transformData) data = transformData(data);
    if (render) renderResponse(data);
    return data;
  } catch (error) {
    renderError(error);
    throw error;
  } finally {
    setLoading(false);
  }
}

async function requestChat(query, { previewOnly = false, render = true } = {}) {
  const clientContext = clientContextSnapshot();
  if (activePlanningNowOverride) clientContext.now = activePlanningNowOverride;
  return runRequest("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: consoleUserId,
      thread_id: consoleThreadId,
      query,
      mode: modeSelect.value,
      publish_to_agenda: false,
      preview_only: previewOnly,
      client_context: clientContext,
    }),
  }, null, { render }).catch(() => null);
}

async function submitQuery(rawQuery, { keepResultMode = false } = {}) {
  let query = rawQuery.trim();
  if (!query) {
    answer.textContent = "请先输入需要安排或调整的任务。";
    return;
  }
  const choice = query.match(/^选\s*([12])$/);
  if (choice) {
    const action = lastSuggestedActions[Number(choice[1]) - 1];
    if (action) {
      query = action.query;
      queryInput.value = action.query;
    }
  }
  beginConversationTurn(query, { keepResultMode });
  queryInput.value = "";
  const data = await requestChat(query);
  if (data) {
    attachMessageIdsToCurrentTurn(data);
    loadConversationThreads().catch(() => {});
  }
  return data;
}

resultEdit?.addEventListener("click", () => {
  setInlineRequestEditing(!resultRequest.classList.contains("is-editing"));
});

resultRerun?.addEventListener("click", async () => {
  const query = resultRequest.classList.contains("is-editing")
    ? resultRequestInput.value.trim()
    : lastResultQuery;
  if (!query || submitButton.disabled) {
    if (!query) resultRequestInput.focus();
    return;
  }
  resultEdit.disabled = true;
  resultRerun.disabled = true;
  resultRerun.textContent = "正在重新规划…";
  try {
    await submitQuery(query, { keepResultMode: true });
  } finally {
    resultEdit.disabled = false;
    resultRerun.disabled = false;
    setInlineRequestEditing(
      resultRequest.classList.contains("is-editing"),
    );
  }
});

resultAddAgenda?.addEventListener("click", async () => {
  const plan = lastResultData?.plan;
  if (!plan?.id || plan.status !== "valid") return;
  const wasPublished = localStorage.getItem(planPublishedKey) === plan.id;
  resultAddAgenda.disabled = true;
  resultAddAgenda.textContent = wasPublished ? "正在打开…" : "正在加入…";
  if (!wasPublished) localStorage.setItem(planPublishedKey, plan.id);
  try {
    scheduleCursorDate = plan.date;
    scheduleViewMode = "day";
    await loadAgendaRange(plan.date, plan.date);
    setActiveWorkspaceView("schedule");
    updateScheduleTabs();
    const dateLabel = `${plan.date.slice(5, 7).replace(/^0/, "")}月${plan.date.slice(8, 10).replace(/^0/, "")}日`;
    saveState.textContent = `已加入 ${dateLabel} 日程`;
    saveState.classList.add("saved");
    resultAddAgenda.textContent = "查看日程";
  } catch (error) {
    if (!wasPublished) localStorage.removeItem(planPublishedKey);
    resultAddAgenda.textContent = wasPublished ? "查看日程" : "加入日程";
    renderDebug(error);
  } finally {
    resultAddAgenda.disabled = false;
  }
});

resultRequestInput?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  resultRerun.click();
});

const resultActionQueries = {
  alternative: "固定课程和锁定安排的时间绝对不变；保留所有任务、时长、截止时间和硬约束，只调整可移动任务，生成另一种可行方案。",
  travel: "固定课程和锁定安排的时间绝对不变；不遗漏任务，只调整可移动任务，优先优化通勤时间并尽量避开拥堵时段。",
  waiting: "固定课程和锁定安排的时间绝对不变；保留任务时长和截止时间，只调整可移动任务，尽量减少行程中的等待时间。",
  order: "固定课程和锁定安排的时间绝对不变；只调整可移动任务的顺序，并说明这样调整的原因。",
};

function planFingerprint(data) {
  return (data?.plan?.items || []).filter(
    (item) => item.item_type !== "meal",
  ).map((item) => [
    item.item_type,
    item.task_id || item.title,
    item.start_at,
    item.end_at,
  ].join("|")).join(";");
}

function planIdleMinutes(plan) {
  const ordered = [...(plan?.items || [])].sort(
    (left, right) => new Date(left.start_at) - new Date(right.start_at),
  );
  return ordered.slice(1).reduce((total, item, index) => {
    const previous = ordered[index];
    const gap = Math.round(
      (new Date(item.start_at) - new Date(previous.end_at)) / 60000,
    );
    return total + Math.max(0, gap);
  }, 0);
}

function renderResultActionOutcome(action, before, after) {
  if (!resultActionStatus || !after?.plan) return false;
  const changed = planFingerprint(before) !== planFingerprint(after);
  const beforeMetrics = before?.plan?.metrics || {};
  const afterMetrics = after.plan.metrics || {};
  const travelSaved = Math.max(
    0,
    (beforeMetrics.travel_minutes || 0) - (afterMetrics.travel_minutes || 0),
  );
  const waitingSaved = Math.max(
    0,
    planIdleMinutes(before?.plan) - planIdleMinutes(after.plan),
  );
  const messages = changed
    ? {
        alternative: "已生成一个候选排法。请比较后选择保留原方案或采用调整方案。",
        travel: travelSaved
          ? `候选方案的通勤时间减少${formatDuration(travelSaved)}。请选择是否采用。`
          : "已生成更侧重通勤衔接的候选方案，请选择是否采用。",
        waiting: waitingSaved
          ? `候选方案的等待时间减少${formatDuration(waitingSaved)}。请选择是否采用。`
          : "已生成更紧凑的候选方案，请选择是否采用。",
        order: "已生成不同任务顺序的候选方案，并重新校验硬约束。",
      }
    : {
        alternative: "当前约束下没有找到同样安全的不同排法，已保留原方案。",
        travel: "当前通勤已是可用路线中的较优结果，无需重复调整。",
        waiting: "当前任务已经连续衔接，没有可进一步压缩的等待时间。",
        order: "其他顺序会影响截止时间或通勤约束，因此保留当前顺序。",
      };
  resultActionStatus.textContent = messages[action] || "规划已重新校验。";
  resultActionStatus.classList.toggle("is-unchanged", !changed);
  resultActionStatus.hidden = false;
  return changed;
}

function currentBaseRequirement() {
  const value = resultRequestText.textContent.trim() || lastResultQuery;
  return value.split(/\n调整要求：/u, 1)[0].trim();
}

resultQuickActions?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-result-action]");
  if (!button || submitButton.disabled || pendingPlanCandidate) return;
  const adjustment = resultActionQueries[button.dataset.resultAction];
  if (!adjustment) return;
  const action = button.dataset.resultAction;
  const before = lastResultData;
  const currentRequirement = currentBaseRequirement();
  const query = `${currentRequirement}\n调整要求：${adjustment}`;
  resultActionStatus.textContent = "正在生成候选方案，原方案不会被覆盖…";
  resultActionStatus.classList.remove("is-unchanged");
  resultActionStatus.hidden = false;
  resultQuickActions.querySelectorAll("button").forEach((item) => {
    item.disabled = true;
    item.classList.toggle("active", item === button);
  });
  try {
    const data = await requestChat(query, {
      previewOnly: true,
      render: false,
    });
    if (!data) return;
    const changed = renderResultActionOutcome(action, before, data);
    if (!changed) {
      renderPlanPanels(before);
      return;
    }
    pendingPlanCandidate = { action, before, candidate: data, query };
    renderPlanPanels(data);
    resultCandidateActions.querySelectorAll("button").forEach((item) => {
      item.disabled = false;
    });
    resultCandidateActions.hidden = false;
    resultAddAgenda.disabled = true;
  } finally {
    if (!pendingPlanCandidate) {
      resultQuickActions.querySelectorAll("button").forEach((item) => {
        item.disabled = false;
        item.classList.remove("active");
      });
    }
  }
});

resultCandidateActions?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-candidate-choice]");
  if (!button || !pendingPlanCandidate || submitButton.disabled) return;
  const pending = pendingPlanCandidate;
  resultCandidateActions.querySelectorAll("button").forEach((item) => {
    item.disabled = true;
  });
  if (button.dataset.candidateChoice === "keep") {
    renderPlanPanels(pending.before);
    pendingPlanCandidate = null;
    resultCandidateActions.hidden = true;
    resultActionStatus.textContent = "已保留原方案，当前日程没有被修改。";
    resultActionStatus.classList.add("is-unchanged");
    resultActionStatus.hidden = false;
    resultQuickActions.querySelectorAll("button").forEach((item) => {
      item.disabled = false;
      item.classList.remove("active");
    });
    resultAddAgenda.disabled = false;
    return;
  }
  resultActionStatus.textContent = "正在采用并保存调整方案…";
  const data = await submitQuery(pending.query, { keepResultMode: true });
  if (data) {
    resultActionStatus.textContent = "已采用调整方案。";
    resultActionStatus.classList.remove("is-unchanged");
    resultActionStatus.hidden = false;
  } else {
    pendingPlanCandidate = null;
    renderPlanPanels(pending.before);
    resultCandidateActions.hidden = true;
    resultAddAgenda.disabled = false;
  }
  resultQuickActions.querySelectorAll("button").forEach((item) => {
    item.disabled = false;
    item.classList.remove("active");
  });
});

submitButton.addEventListener("click", async () => {
  await submitQuery(queryInput.value);
});

queryInput.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (submitButton.disabled) return;
  await submitQuery(queryInput.value);
});

resetButton.addEventListener("click", async () => {
  setLoading(true);
  try {
    const response = await fetch("/api/v1/demos/reset", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw data;
    clearConversationStream();
    queryInput.value = "";
    timeline.className = "timeline empty";
    timeline.textContent = "演示已复位，请从案例一开始。";
    resultSummary.innerHTML = "";
    resultSummary.hidden = true;
    resultRequest.hidden = true;
    resultDetails.hidden = true;
    setResultMode(false);
    planTitle.textContent = "日程时间轴";
    taskStatuses.innerHTML = "";
    execution.className = "execution-list empty";
    execution.textContent = "运行后显示五个处理步骤。";
    constraints.className = "check-list empty";
    constraints.textContent = "生成后显示检查结果。";
    diff.innerHTML = "";
    adjustmentPanel.classList.remove("has-changes");
    adjustment.textContent = "当前没有计划变更。";
    answer.textContent = data.message;
    answer.classList.remove("muted");
    warnings.textContent = "暂时没有提醒。";
    warnings.className = "warnings muted";
    freshness.innerHTML = "";
    renderSuggestedActions([]);
    renderInsights([]);
    renderDebug(null);
    localStorage.removeItem(planSnapshotKey);
    saveState.textContent = "尚未生成当前计划";
    saveState.classList.remove("saved");
  } catch (error) {
    renderError(error);
  } finally {
    setLoading(false);
  }
});

async function loadDemos() {
  const response = await fetch("/api/v1/demos");
  const demos = await response.json();
  const demoMarkup = demos.map((demo, index) => `
    <button data-demo="${escapeHtml(demo.id)}">
      <span class="demo-play" aria-hidden="true">▶</span>
      <span>${escapeHtml(demo.title)}</span>
      <small>案例${"一二三四"[index] || index + 1}</small>
    </button>
  `).join("");
  demoButtons.innerHTML = demoMarkup;
  sidebarDemoButtons.innerHTML = demoMarkup;
  const bindDemoToCurrentVisitor = (data) => {
    const bindPlan = (plan) => plan ? {
      ...plan,
      user_id: consoleUserId,
      thread_id: consoleThreadId,
    } : plan;
    return {
      ...data,
      thread_id: consoleThreadId,
      plan: bindPlan(data.plan),
      previous_plan: bindPlan(data.previous_plan),
    };
  };
  const runDemo = async (button, demo) => {
    if (!demo || submitButton.disabled) return;
    const keepResultMode = document.body.classList.contains("has-plan-result");
    queryInput.value = demo.query;
    modeSelect.value = "auto";
    beginConversationTurn(demo.query, { keepResultMode });
    document.querySelectorAll("[data-demo]")
      .forEach((item) => item.classList.toggle(
        "active",
        item.dataset.demo === demo.id,
      ));
    const data = await runRequest(
      `/api/v1/demos/${demo.id}/run`,
      { method: "POST" },
      bindDemoToCurrentVisitor,
    ).catch(() => {});
    if (data) {
      activePlanningNowOverride = data.time_context?.now || null;
      loadConversationThreads().catch(() => {});
    }
  };
  const buttons = [
    ...demoButtons.querySelectorAll("button"),
    ...sidebarDemoButtons.querySelectorAll("button"),
  ];
  buttons.forEach((button) => {
    button.addEventListener("click", async () => {
      const demo = demos.find((item) => item.id === button.dataset.demo);
      await runDemo(button, demo);
    });
  });
}

function parseWeeklyDate(rawDate) {
  const [year, month, day] = String(rawDate).split("-").map(Number);
  return { year, month, day };
}

function addWeeklyDays(rawDate, offset) {
  const { year, month, day } = parseWeeklyDate(rawDate);
  const value = new Date(Date.UTC(year, month - 1, day + offset, 12));
  return value.toISOString().slice(0, 10);
}

function weeklyDateLabel(rawDate) {
  const { year, month, day } = parseWeeklyDate(rawDate);
  const value = new Date(Date.UTC(year, month - 1, day, 12));
  const weekday = "日一二三四五六"[value.getUTCDay()];
  return `${month}月${day}日 · 周${weekday}`;
}

function weeklyTimeLabel(rawValue) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(rawValue));
}

function nextWeeklyMonday() {
  const now = new Date(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  );
  const weekday = now.getUTCDay() || 7;
  const daysUntilMonday = weekday === 1 ? 0 : 8 - weekday;
  now.setUTCDate(now.getUTCDate() + daysUntilMonday);
  return now.toISOString().slice(0, 10);
}

const weeklyLocationLabels = {
  library: "图书馆",
  library_floor_6_12: "图书馆六层或十二层",
  library_floor_7_11: "图书馆七至十一层",
  teaching_building_6: "第六教学楼",
  parcel_station: "菜鸟驿站",
  sf_express: "顺丰快递点",
  jd_express: "京东快递点",
  canteen: "学生餐厅",
  track: "东操场",
  gym_south_track: "体育馆副馆南侧跑道",
  northwest_track: "西北田径场",
  gym_main: "体育馆主馆",
  gym_comprehensive: "综合馆",
  laboratory: "实验室",
  student_dormitory: "学生公寓",
  campus_hospital: "校医院",
};

function weeklyLocationLabel(rawValue) {
  if (!rawValue) return "";
  if (weeklyLocationLabels[rawValue]) return weeklyLocationLabels[rawValue];
  return /[\u3400-\u9fff]/.test(rawValue) ? rawValue : "";
}

function renderWeeklyPlan(data) {
  const plan = data.weekly_plan;
  const capacitySummary = data.capacity_summary || {};
  const statusLabels = {
    valid: "本周可执行",
    at_risk: "存在挤压风险",
    infeasible: "容量不足",
  };
  weeklyState.textContent = statusLabels[plan.status] || "已生成";
  weeklyState.classList.toggle("ready", plan.status === "valid");
  weeklySummary.classList.remove("muted");
  weeklySummary.innerHTML = `
    <strong>${escapeHtml(data.answer)}</strong>
    <div class="weekly-metrics">
      <span>目标 ${plan.goals.length} 项</span>
      <span>时间块 ${plan.allocations.length} 个</span>
      <span>已分配 ${Math.round(plan.metrics.allocated_duration_min / 6) / 10} 小时</span>
      <span>未分配 ${plan.metrics.unallocated_duration_min} 分钟</span>
    </div>
    ${capacitySummary.source === "personal_context" ? `
      <div class="weekly-context">
        <span>${capacitySummary.timetable_applied
          ? `已扣除 ${capacitySummary.excluded_course_count || 0} 段个人课程`
          : "尚未启用个人课表"}</span>
        ${(capacitySummary.memory_labels || []).map((label) =>
          `<span>已参考${escapeHtml(label)}</span>`,
        ).join("")}
      </div>
      <p class="weekly-context-note">${escapeHtml(
        (capacitySummary.notes || []).join("；"),
      )}</p>
    ` : ""}
  `;
  const goals = new Map(plan.goals.map((goal) => [goal.id, goal]));
  const stages = new Map(
    plan.goals.flatMap((goal) =>
      goal.stages.map((stage) => [stage.id, stage]),
    ),
  );
  const byDate = plan.allocations.reduce((result, item) => {
    (result[item.date] ||= []).push(item);
    return result;
  }, {});
  const allDates = Array.from(
    { length: 7 },
    (_, offset) => addWeeklyDays(plan.week_start, offset),
  );
  weeklyGrid.innerHTML = allDates.map((rawDate) => {
    const items = byDate[rawDate] || [];
    return `
      <section class="weekly-day ${items.length ? "" : "weekly-day-empty"}">
        <header>
          <strong>${escapeHtml(weeklyDateLabel(rawDate))}</strong>
          <small>${items.reduce(
            (sum, item) => sum + item.allocated_duration_min,
            0,
          )} 分钟</small>
        </header>
        <div>
          ${items.length ? items.map((item) => {
            const goal = goals.get(item.goal_id);
            const stage = stages.get(item.stage_id);
            const locationLabel = weeklyLocationLabel(item.location_id);
            return `
              <article class="weekly-block">
                <time>${escapeHtml(weeklyTimeLabel(item.earliest_start))}
                  — ${escapeHtml(weeklyTimeLabel(item.latest_end))}</time>
                <strong>${escapeHtml(stage?.title || goal?.title || "本周任务")}</strong>
                <small>${escapeHtml(goal?.title || "")}${
                  locationLabel
                    ? ` · ${escapeHtml(locationLabel)}`
                    : ""
                }</small>
              </article>
            `;
          }).join("") : "<p>留作缓冲、休息或临时变化</p>"}
        </div>
      </section>
    `;
  }).join("");
  weeklyRisks.innerHTML = plan.issues.length
    ? plan.issues.map((issue) => `
      <div class="warning ${issue.severity === "error" ? "error" : ""}">
        <strong>本周风险</strong>
        <span>${escapeHtml(issue.message)}</span>
      </div>
    `).join("")
    : `
      <div class="weekly-safe">
        <strong>本周目标均已纳入</strong>
        <span>每天执行前仍会根据实时天气、通勤和临时校历再次检查。</span>
      </div>
    `;
  renderDebug(data);
}

async function loadWeeklyDemos() {
  const response = await fetch("/api/v1/weeks/demos/catalog");
  const demos = await response.json();
  if (!response.ok) throw demos;
  weeklyDemoButtons.innerHTML = demos.map((demo) => `
    <button
      class="ghost"
      data-weekly-demo="${escapeHtml(demo.id)}"
      title="${escapeHtml(demo.description)}"
    >${escapeHtml(demo.title)}</button>
  `).join("");
  weeklyDemoButtons.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      weeklyDemoButtons.querySelectorAll("button").forEach((item) =>
        item.classList.toggle("active", item === button),
      );
      button.disabled = true;
      weeklyState.textContent = "正在分配…";
      try {
        const response = await fetch(
          `/api/v1/weeks/demos/${button.dataset.weeklyDemo}/run`
            + `?user_id=${encodeURIComponent(consoleUserId)}`,
          { method: "POST" },
        );
        const data = await response.json();
        if (!response.ok) throw data;
        renderWeeklyPlan(data);
      } catch (error) {
        weeklyState.textContent = "生成失败";
        weeklySummary.textContent = error?.error?.message
          || "周计划暂时没有生成成功，请稍后重试。";
        weeklySummary.classList.remove("muted");
        renderDebug(error);
      } finally {
        button.disabled = false;
      }
    });
  });
}

weeklyGenerate.addEventListener("click", async () => {
  const query = weeklyQuery.value.trim();
  if (!query) {
    weeklySummary.textContent = "先告诉我这一周最想完成的目标吧。";
    weeklySummary.classList.remove("muted");
    weeklyQuery.focus();
    return;
  }
  if (!weeklyStart.value) weeklyStart.value = nextWeeklyMonday();
  weeklyGenerate.disabled = true;
  weeklyState.textContent = "正在理解目标…";
  weeklySummary.textContent = (
    "正在结合你的课表、校历和长期偏好，计算这一周真正可用的时间。"
  );
  weeklySummary.classList.remove("muted");
  try {
    const response = await fetch("/api/v1/weeks/plan/from-text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: consoleUserId,
        campus_id: currentCampusProfile?.id || "hdu_xiasha",
        week_start: weeklyStart.value,
        timezone: "Asia/Shanghai",
        query,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw data;
    renderWeeklyPlan(data);
    weeklyGenerate.textContent = "按新要求重新规划本周";
  } catch (error) {
    const questions = (error?.error?.details || [])
      .map((item) => item.question)
      .filter(Boolean);
    weeklyState.textContent = questions.length ? "需要确认" : "生成失败";
    weeklySummary.innerHTML = questions.length
      ? `
        <strong>${escapeHtml(error?.error?.message || "还需要确认一项信息。")}</strong>
        <ul>${questions.map((item) =>
          `<li>${escapeHtml(item)}</li>`,
        ).join("")}</ul>
      `
      : escapeHtml(
        error?.error?.message
          || "这一周暂时没有排成功，请稍后再试一次。",
      );
    weeklySummary.classList.remove("muted");
    renderDebug(error);
  } finally {
    weeklyGenerate.disabled = false;
  }
});

function parseMemoryValue(key, rawValue) {
  const value = rawValue.trim();
  if (!value) throw new Error("请先填写想保存的偏好。");
  if (key === "buffer_min") {
    const minutes = Number(value.match(/\d+/)?.[0]);
    if (!Number.isFinite(minutes) || minutes < 0 || minutes > 60) {
      throw new Error("缓冲时间请填写0到60分钟。");
    }
    return minutes;
  }
  if (key === "walking_speed") {
    const normalized = { 慢: "slow", 正常: "normal", 快: "fast" }[value];
    if (!normalized) throw new Error("步行节奏请填写：慢、正常或快。");
    return normalized;
  }
  if (key === "transport_mode") {
    const normalized = {
      步行: "walk",
      自行车: "bicycle",
      骑行: "bicycle",
      电瓶车: "electrobike",
      电动车: "electrobike",
    }[value];
    if (!normalized) {
      throw new Error("常用出行方式请填写：步行、自行车或电瓶车。");
    }
    return normalized;
  }
  if (key === "avoid_congestion") {
    if (["是", "需要", "开启", "true"].includes(value.toLowerCase())) return true;
    if (["否", "不需要", "关闭", "false"].includes(value.toLowerCase())) return false;
    throw new Error("这一项请填写“是”或“否”。");
  }
  if (key === "schedule_pace") {
    const normalized = {
      宽松: "relaxed",
      松: "relaxed",
      适中: "balanced",
      正常: "balanced",
      紧凑: "compact",
      紧: "compact",
    }[value];
    if (!normalized) throw new Error("日程节奏请填写：宽松、适中或紧凑。");
    return normalized;
  }
  if (key === "activity_location") {
    const entries = value.split(/[；;\n]+/).map((item) => item.trim()).filter(Boolean);
    const mappings = entries.map((entry) => {
      const matched = entry.match(/^(.+?)\s*(?:→|->|：|:)\s*(.+)$/);
      if (!matched) {
        throw new Error("请按“事项 → 地点”填写，例如：跑步 → 东操场。");
      }
      return { activity: matched[1].trim(), location: matched[2].trim() };
    });
    if (mappings.some((item) => !item.activity || !item.location)) {
      throw new Error("事情和地点都不能留空。");
    }
    return mappings;
  }
  if (key === "preferred_study_period") {
    const normalized = {
      上午: "morning",
      早上: "morning",
      下午: "afternoon",
      晚上: "evening",
      晚间: "evening",
    }[value];
    if (!normalized) throw new Error("高效学习时段请填写：上午、下午或晚上。");
    return normalized;
  }
  if ([
    "usual_bedtime",
    "usual_wake_time",
    "usual_lunch_time",
    "usual_dinner_time",
  ].includes(key)) {
    const matched = value.match(/^([01]?\d|2[0-3])[:：]([0-5]\d)$/);
    if (!matched) {
      throw new Error("请按24小时制填写，例如：23:30或07:00。");
    }
    return `${matched[1].padStart(2, "0")}:${matched[2]}`;
  }
  if (key === "sleep_goal_hours") {
    const hours = Number(value.match(/\d+(?:\.\d+)?/)?.[0]);
    if (!Number.isFinite(hours) || hours < 4 || hours > 12) {
      throw new Error("希望睡眠时长请填写4到12小时。");
    }
    return hours;
  }
  return value;
}

function displayMemoryValue(key, value) {
  if (key === "buffer_min") return `${value}分钟`;
  if (key === "walking_speed") {
    return { slow: "慢", normal: "正常", fast: "快" }[value] || value;
  }
  if (key === "transport_mode") {
    return {
      walk: "步行",
      bicycle: "自行车",
      electrobike: "电瓶车",
    }[value] || value;
  }
  if (key === "avoid_congestion") {
    return value ? "是" : "否";
  }
  if (key === "schedule_pace") {
    return {
      relaxed: "宽松",
      balanced: "适中",
      compact: "紧凑",
    }[value] || value;
  }
  if (key === "activity_location") {
    const mappings = normalizeActivityLocations(value);
    return mappings.map((item) => `${item.activity} → ${item.location}`).join("；");
  }
  if (key === "preferred_study_period") {
    return {
      morning: "上午",
      afternoon: "下午",
      evening: "晚上",
    }[value] || value;
  }
  if ([
    "usual_bedtime",
    "usual_wake_time",
    "usual_lunch_time",
    "usual_dinner_time",
  ].includes(key)) return value;
  if (key === "sleep_goal_hours") return `${value}小时`;
  if (Array.isArray(value)) return value.join("、");
  return String(value);
}

function normalizeActivityLocations(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => (
      item && typeof item.activity === "string" && typeof item.location === "string"
    )).map((item) => ({
      activity: item.activity.trim(),
      location: item.location.trim(),
    })).filter((item) => item.activity && item.location);
  }
  if (value && typeof value === "object") {
    return Object.entries(value).map(([activity, location]) => ({
      activity: String(activity).trim(),
      location: String(location).trim(),
    })).filter((item) => item.activity && item.location);
  }
  return [];
}

function mergeActivityLocations(existing, additions) {
  const merged = new Map(
    normalizeActivityLocations(existing).map((item) => [item.activity, item]),
  );
  additions.forEach((item) => merged.set(item.activity, item));
  return [...merged.values()];
}

function updateMemoryPlaceholder() {
  const definition = memoryDefinitions[memoryType.value];
  memoryValue.placeholder = definition?.placeholder || "填写偏好";
}

async function loadMemories() {
  const response = await fetch(`/api/v1/users/${consoleUserId}/memories`);
  const data = await response.json();
  if (!response.ok) throw data;
  let items = data.items || [];
  const localItems = readLocalSnapshot(memorySnapshotKey, [])
    .filter((item) => !retiredMemoryKeys.has(item.key));
  items = items.filter((item) => !retiredMemoryKeys.has(item.key));
  if (items.length) {
    writeLocalSnapshot(memorySnapshotKey, items);
  } else if (localItems.length) {
    items = localItems;
  }
  loadedMemories = items;
  memoryList.classList.toggle("muted", items.length === 0);
  memoryList.innerHTML = items.length
    ? items.map((item) => `
      <div class="memory-item ${item.enabled ? "" : "disabled"}">
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <small>${escapeHtml(displayMemoryValue(item.key, item.value))}</small>
        </div>
        <div class="memory-actions">
          <button data-memory-edit="${escapeHtml(item.id)}">修改</button>
          <button data-memory-toggle="${escapeHtml(item.id)}">
            ${item.enabled ? "停用" : "启用"}
          </button>
          <button class="danger-link" data-memory-delete="${escapeHtml(item.id)}">
            删除
          </button>
        </div>
      </div>
    `).join("")
    : "还没有保存长期偏好。";
  memoryList.querySelectorAll("[data-memory-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items.find((value) => value.id === button.dataset.memoryEdit);
      if (!item) return;
      memoryType.value = item.key in memoryDefinitions ? item.key : "custom_note";
      memoryValue.value = displayMemoryValue(item.key, item.value);
      editingMemoryKey = item.key;
      updateMemoryPlaceholder();
      memoryValue.focus();
    });
  });
  memoryList.querySelectorAll("[data-memory-toggle]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = items.find((value) => value.id === button.dataset.memoryToggle);
      if (!item) return;
      await fetch(`/api/v1/users/${consoleUserId}/memories/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !item.enabled }),
      });
      writeLocalSnapshot(
        memorySnapshotKey,
        items.map((value) => value.id === item.id
          ? { ...value, enabled: !value.enabled }
          : value),
      );
      await loadMemories();
      await loadAgenda(agendaDate.value || shanghaiDateString());
    });
  });
  memoryList.querySelectorAll("[data-memory-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(
        `/api/v1/users/${consoleUserId}/memories/${button.dataset.memoryDelete}`,
        { method: "DELETE" },
      );
      writeLocalSnapshot(
        memorySnapshotKey,
        items.filter((value) => value.id !== button.dataset.memoryDelete),
      );
      await loadMemories();
      await loadAgenda(agendaDate.value || shanghaiDateString());
    });
  });
}

memoryType.addEventListener("change", () => {
  editingMemoryKey = null;
  memoryValue.value = "";
  updateMemoryPlaceholder();
});
memorySave.addEventListener("click", async () => {
  const definition = memoryDefinitions[memoryType.value];
  try {
    let parsedValue = parseMemoryValue(memoryType.value, memoryValue.value);
    if (memoryType.value === "activity_location" && editingMemoryKey !== "activity_location") {
      const existing = loadedMemories.find((item) => item.key === "activity_location");
      parsedValue = mergeActivityLocations(existing?.value, parsedValue);
    }
    const response = await fetch(`/api/v1/users/${consoleUserId}/memories`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category: definition.category,
        key: memoryType.value,
        label: definition.label,
        value: parsedValue,
        enabled: true,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw data;
    const current = readLocalSnapshot(memorySnapshotKey, []);
    writeLocalSnapshot(
      memorySnapshotKey,
      [
        data,
        ...current.filter((item) => item.key !== data.key),
      ],
    );
    memoryValue.value = "";
    editingMemoryKey = null;
    await loadMemories();
    await loadAgenda(agendaDate.value || shanghaiDateString());
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : error?.error?.message || "这条记忆暂时没有保存成功。";
    memoryList.textContent = message;
    memoryList.classList.remove("muted");
    renderDebug(error);
  }
});

function timetableWeekdayLabel(value) {
  return `周${"一二三四五六日"[Number(value) - 1] || value}`;
}

function hduhelpTermLabel(term) {
  const semester = { 1: "第一学期", 2: "第二学期", 3: "短学期" }[
    term.semester
  ] || `第${term.semester}学期`;
  return `${term.school_year} · ${semester}`;
}

function renderHduHelpConnection(data) {
  const connected = Boolean(data?.connected);
  hduhelpBadge.textContent = connected ? "已连接" : "未连接";
  hduhelpBadge.classList.toggle("connected", connected);
  hduhelpConnectForm.hidden = connected;
  hduhelpSyncForm.hidden = !connected;
  hduhelpAvailableTerms = data?.available_terms || [];
  hduhelpState.classList.remove("error", "ready");
  const labels = {
    course: "课程",
    library_reservation: "自习预约",
    second_classroom: "二课",
    exam: "考试",
    volunteer: "志愿活动",
    timetable_terms: "学期课表",
  };
  hduhelpDataSummary.innerHTML = Object.entries(labels)
    .map(([key, label]) => [label, Number(data?.synced_counts?.[key] || 0)])
    .filter(([, count]) => count > 0)
    .map(([label, count]) => `<span>${escapeHtml(label)} ${count}</span>`)
    .join("");
  if (!connected) {
    hduhelpState.textContent = "登录易程智策后，可在这里绑定自己的杭助个人访问令牌。";
    return;
  }
  hduhelpState.textContent = data.last_synced_at
    ? `已连接${data.display_name ? `：${data.display_name}` : ""}，校园数据已同步。`
    : `已连接${data.display_name ? `：${data.display_name}` : ""}，系统会自动同步全部可用学期和校园数据。`;
  hduhelpState.classList.add("ready");
}

async function loadHduHelpConnection() {
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/connections/hduhelp`,
  );
  const data = await response.json();
  if (!response.ok) throw data;
  renderHduHelpConnection(data);
  const syncedAt = Date.parse(data.last_synced_at || "");
  const needsRefresh = data.connected && hduhelpAvailableTerms.length > 0 && (
    !Number.isFinite(syncedAt) || Date.now() - syncedAt > 15 * 60 * 1000
  );
  const autoSyncKey = `yicheng_hduhelp_autosync_${consoleUserId}`;
  if (needsRefresh && sessionStorage.getItem(autoSyncKey) !== "running") {
    sessionStorage.setItem(autoSyncKey, "running");
    setTimeout(() => hduhelpSync.click(), 0);
  }
}

hduhelpConnect.addEventListener("click", async () => {
  const token = hduhelpToken.value.trim();
  if (!token) {
    hduhelpState.textContent = "请先粘贴自己的个人访问令牌。";
    hduhelpState.classList.add("error");
    hduhelpToken.focus();
    return;
  }
  hduhelpConnect.disabled = true;
  hduhelpConnect.textContent = "正在验证…";
  hduhelpState.textContent = "正在核验身份和可用学期，不会读取或显示令牌内容。";
  hduhelpState.classList.remove("error", "ready");
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/connections/hduhelp`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    hduhelpToken.value = "";
    renderHduHelpConnection(data);
    setTimeout(() => hduhelpSync.click(), 0);
  } catch (error) {
    hduhelpState.textContent = error?.error?.message
      || "杭电助手暂时没有连接成功。";
    hduhelpState.classList.add("error");
    renderDebug(error);
  } finally {
    hduhelpConnect.disabled = false;
    hduhelpConnect.textContent = "验证并连接";
  }
});

hduhelpDisconnect.addEventListener("click", async () => {
  hduhelpDisconnect.disabled = true;
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/connections/hduhelp`,
      { method: "DELETE" },
    );
    if (!response.ok && response.status !== 404) {
      const data = await response.json();
      throw data;
    }
    renderHduHelpConnection({ connected: false, available_terms: [] });
  } catch (error) {
    hduhelpState.textContent = error?.error?.message || "暂时无法断开连接。";
    hduhelpState.classList.add("error");
    renderDebug(error);
  } finally {
    hduhelpDisconnect.disabled = false;
  }
});

hduhelpSync.addEventListener("click", async () => {
  hduhelpSync.disabled = true;
  hduhelpSync.textContent = "正在同步…";
  hduhelpState.textContent = "正在同步全部学期、课程、预约、考试和校园数据。";
  hduhelpState.classList.remove("error", "ready");
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/connections/hduhelp/sync`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    writeLocalSnapshot(timetableSnapshotKey, data);
    renderTimetableTerms(data.terms || []);
    const warning = data.warnings?.length ? `；${data.warnings.join("；")}` : "";
    hduhelpState.textContent = `已同步 ${data.imported_count} 个课程时段和校园安排${warning}`;
    hduhelpState.classList.add("ready");
    sessionStorage.removeItem(`yicheng_hduhelp_autosync_${consoleUserId}`);
    await loadHduHelpConnection();
    await loadAgenda(agendaDate.value || shanghaiDateString());
  } catch (error) {
    hduhelpState.textContent = error?.error?.message
      || "杭电助手课表暂时没有同步成功。";
    hduhelpState.classList.add("error");
    renderDebug(error);
  } finally {
    hduhelpSync.disabled = false;
    hduhelpSync.textContent = "同步全部校园数据";
  }
});

function renderTimetable(data) {
  const entries = data.entries || [];
  timetableSummary.classList.toggle("muted", entries.length === 0);
  if (!entries.length) {
    timetableSummary.textContent = "当前还没有同步个人课表。";
    return;
  }
  const grouped = new Map();
  [...entries]
    .sort(
      (left, right) =>
        left.weekday - right.weekday
        || left.start_period - right.start_period
        || left.end_period - right.end_period
        || left.course_name.localeCompare(right.course_name, "zh-CN"),
    )
    .forEach((entry) => {
    if (!grouped.has(entry.weekday)) grouped.set(entry.weekday, []);
    grouped.get(entry.weekday).push(entry);
  });
  const termRange = data.timetable?.term_start && data.timetable?.term_end
    ? `${data.timetable.term_start}—${data.timetable.term_end}`
    : "";
  timetableSummary.innerHTML = `
    <div class="timetable-status">
      <strong>${escapeHtml(data.timetable?.name || "我的课表")}</strong>
      <span>${termRange ? `${escapeHtml(termRange)} · ` : ""}${entries.length}个课程时段 · 杭助同步</span>
    </div>
    ${[...grouped.entries()].map(([weekday, values]) => `
      <div class="timetable-day">
        <strong>${timetableWeekdayLabel(weekday)}</strong>
        <div>
          ${values.map((entry) => `
            <span>${escapeHtml(entry.course_name)} · 第${entry.start_period}${
              entry.end_period === entry.start_period
                ? ""
                : `—${entry.end_period}`
            }节${entry.location ? ` · ${escapeHtml(entry.location)}` : ""}${
              entry.weeks?.length
                ? ` · 第${escapeHtml(entry.weeks.join("、"))}周`
                : ""
            }</span>
          `).join("")}
        </div>
      </div>
    `).join("")}
  `;
}

let hduhelpAvailableTerms = [];
let syncedTimetableTerms = [];

function timetableTermKey(term) {
  return `${term.school_year}|${term.semester}`;
}

function renderTimetableTerms(terms, preferredKey = "") {
  syncedTimetableTerms = Array.isArray(terms) ? terms : [];
  timetableTermControls.hidden = syncedTimetableTerms.length === 0;
  if (!syncedTimetableTerms.length) {
    renderTimetable({ entries: [] });
    return;
  }
  timetableTermView.innerHTML = syncedTimetableTerms.map((term) => `
    <option value="${escapeHtml(timetableTermKey(term))}">
      ${escapeHtml(hduhelpTermLabel(term))}${term.current ? "（当前）" : ""}
    </option>
  `).join("");
  const selected = syncedTimetableTerms.find(
    (term) => timetableTermKey(term) === preferredKey,
  ) || syncedTimetableTerms.find((term) => term.current) || syncedTimetableTerms[0];
  timetableTermView.value = timetableTermKey(selected);
  renderTimetable({
    timetable: {
      name: selected.name,
      term_start: selected.term_start,
      term_end: selected.term_end,
    },
    entries: selected.entries || [],
  });
}

timetableTermView?.addEventListener("change", () => {
  const selected = syncedTimetableTerms.find(
    (term) => timetableTermKey(term) === timetableTermView.value,
  );
  if (!selected) return;
  renderTimetable({
    timetable: {
      name: selected.name,
      term_start: selected.term_start,
      term_end: selected.term_end,
    },
    entries: selected.entries || [],
  });
});

async function loadTimetable() {
  const hduResponse = await fetch(
    `/api/v1/users/${consoleUserId}/connections/hduhelp/timetables`,
  );
  if (hduResponse.ok) {
    const hduData = await hduResponse.json();
    if (hduData.terms?.length) {
      renderTimetableTerms(hduData.terms);
      return;
    }
  }
  const response = await fetch(`/api/v1/users/${consoleUserId}/timetable`);
  const data = await response.json();
  if (!response.ok) throw data;
  const timetableData = data.entries?.length
    ? data
    : readLocalSnapshot(timetableSnapshotKey, data);
  if (data.entries?.length) {
    writeLocalSnapshot(timetableSnapshotKey, data);
  }
  renderTimetable(timetableData);
}

async function checkHealth() {
  try {
    const response = await fetch("/api/v1/health");
    const data = await response.json();
    health.textContent = data.status === "ok" ? "服务正常" : "服务降级";
    health.classList.toggle("ok", data.status === "ok");
    if (data.server_time) {
      serverClockBaseMs = new Date(data.server_time).getTime();
      serverClockFetchedAtMs = Date.now();
      renderClock();
    }
  } catch {
    health.textContent = "服务不可用";
    clock.textContent = "北京时间暂不可用";
  }
}

async function initializeApp() {
  initializeWorkspaceNavigation();
  renderConversationHistory();
  checkHealth();
  setInterval(renderClock, 30000);
  updateMemoryPlaceholder();
  renderPersonalizationState();
  loadCampus().catch((error) => {
    campusState.textContent = "读取失败";
    campusSummary.textContent = "暂时无法读取校园设置。";
    renderDebug(error);
  });
  const accessGranted = await initializeAccess();
  if (!accessGranted) return;
  const session = configureSessionWorkspace();
  await loadConversationThreads().catch(() => {
    serverConversationThreads = [];
    renderConversationHistory();
  });
  if (requestedThreadId && serverConversationThreads.some(
    (item) => item.id === requestedThreadId,
  )) {
    await openConversationThread(requestedThreadId).catch((error) => {
      renderError(error);
    });
  }
  await loadDemos().catch(() => {
    demoButtons.textContent = "案例加载失败";
  });
  agendaDate.value = shanghaiDateString();
  scheduleCursorDate = agendaDate.value;
  weeklyStart.value = nextWeeklyMonday();
  serviceWorkerRegistration().catch(() => {});
  loadReminderSettings().catch((error) => {
    reminderState.textContent = "提醒设置暂时无法读取。";
    renderDebug(error);
  });
  loadAgenda(agendaDate.value).catch((error) => {
    agendaState.textContent = "读取失败";
    agendaList.textContent = "个人日程暂时没有加载成功，请稍后刷新。";
    renderDebug(error);
  });
  loadWeeklyDemos().catch((error) => {
    weeklyDemoButtons.textContent = "复杂周场景暂时无法读取";
    renderDebug(error);
  });
  loadMemories().catch((error) => renderDebug(error));
  loadHduHelpConnection().catch((error) => renderDebug(error));
  loadTimetable().catch((error) => renderDebug(error));
}

initializeApp();
