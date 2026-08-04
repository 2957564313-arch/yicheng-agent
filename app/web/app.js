const accessTokenKey = "yicheng_access_token";
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
const resultDetails = $("#result-details");
const resultConstraints = $("#result-constraints");
const resultConstraintTotal = $("#result-constraint-total");
const resultSources = $("#result-sources");
const resultQuickActions = $("#result-quick-actions");
const resultActionStatus = $("#result-action-status");
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
const profileExport = $("#profile-export");
const profileImportFile = $("#profile-import-file");
const profileRestore = $("#profile-restore");
const profileBackupState = $("#profile-backup-state");
const personalizationToggle = $("#personalization-toggle");
const personalizationReset = $("#personalization-reset");
const personalizationState = $("#personalization-state");
const timetableName = $("#timetable-name");
const termStart = $("#term-start");
const termEnd = $("#term-end");
const timetableFile = $("#timetable-file");
const timetableImport = $("#timetable-import");
const timetableConfirm = $("#timetable-confirm");
const timetableSummary = $("#timetable-summary");
const timetableClear = $("#timetable-clear");
const calendarDate = $("#calendar-date");
const calendarAction = $("#calendar-action");
const calendarWeekday = $("#calendar-weekday");
const calendarLabel = $("#calendar-label");
const calendarSave = $("#calendar-save");
const calendarList = $("#calendar-list");
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
const loginMessage = $("#login-message");
const logoutButton = $("#logout");
const adjustmentPanel = $(".adjustment-panel");
const historySidebar = $("#history-sidebar");
const historyList = $("#history-list");
const historyEmpty = $("#history-empty");
const historyToggle = $("#history-toggle");
const historyClose = $("#history-close");
const newConversation = $("#new-conversation");
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
let scheduleViewMode = "day";
let scheduleCursorDate = null;
let lastAgendaData = null;
let activeConversationQuery = "";
let activeConversationAnswer = "";
let lastResultQuery = "";
let lastResultData = null;
const consoleUserId = getOrCreateLocalIdentity(
  "yicheng_user_id",
  "visitor",
);
const consoleThreadId = getOrCreateLocalIdentity(
  "yicheng_thread_id",
  "thread",
);
let lastSuggestedActions = [];
let lastDebugPayload = null;
let serverClockBaseMs = null;
let serverClockFetchedAtMs = null;
let pendingTimetableImport = null;
let pendingProfileBackup = null;
let currentCampusProfile = null;
const memorySnapshotKey = "yicheng_memory_snapshot";
const timetableSnapshotKey = "yicheng_timetable_snapshot";
const calendarSnapshotKey = "yicheng_calendar_snapshot";
const planSnapshotKey = "yicheng_current_plan_snapshot";
const campusSnapshotKey = "yicheng_campus_snapshot";
const behaviorHistoryKey = "yicheng_behavior_history";
const suggestionFeedbackKey = "yicheng_suggestion_feedback";
const personalizationEnabledKey = "yicheng_personalization_enabled";
const conversationHistoryKey = "yicheng_conversation_history";
const shownReminderKey = "yicheng_shown_reminders";
const reminderSettingsSnapshotKey = "yicheng_reminder_settings_snapshot";
let currentReminderSettings = null;
let reminderPollTimer = null;

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
  const items = readLocalSnapshot(conversationHistoryKey, [])
    .filter((item) => item && item.query)
    .slice(0, 24);
  historyEmpty.hidden = items.length > 0;
  historyList.innerHTML = items.map((item, index) => `
    <button class="history-item" type="button" data-history-index="${index}" aria-label="???????${escapeHtml(item.query)}">
      <strong>${escapeHtml(item.query)}</strong>
      <small>${escapeHtml(item.answer || "?????")}</small>
    </button>
  `).join("");
}

function recordConversationHistory(query, answerText, responseData = null) {
  const normalized = String(query || "").trim();
  if (!normalized) return;
  const current = readLocalSnapshot(conversationHistoryKey, [])
    .filter((item) => item && item.query && item.query !== normalized);
  current.unshift({
    query: normalized,
    answer: String(answerText || "").replace(/\s+/g, " ").slice(0, 120),
    response: responseData || null,
    created_at: new Date().toISOString(),
  });
  writeLocalSnapshot(conversationHistoryKey, current.slice(0, 24));
  renderConversationHistory();
}

function appendConversationMessage(role, text) {
  if (!conversationStream || !String(text || "").trim()) return;
  const isUser = role === "user";
  conversationStream.hidden = false;
  conversationStream.insertAdjacentHTML(
    "beforeend",
    `<article class="conversation-message ${isUser ? "user-message" : "assistant-message"}">
      <span class="message-avatar" aria-hidden="true">${isUser ? "?" : "?"}</span>
      <div class="message-body">
        <p class="message-role">${isUser ? "?" : "????"}</p>
        <div class="message-content">${escapeHtml(String(text))}</div>
      </div>
    </article>`,
  );
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
  if (!keepResultMode) document.body.classList.remove("has-plan-result");
  answer.textContent = "???????????????????";
  answer.classList.add("muted");
  assistantActions.innerHTML = "";
  freshness.innerHTML = "";
}

function completeConversationTurn(answerText) {
  if (!activeConversationQuery) return;
  activeConversationAnswer = String(answerText || "").trim();
}

function restoreConversationSnapshot(query, answerText) {
  clearConversationStream();
  appendConversationMessage("user", query);
  activeConversationQuery = String(query || "").trim();
  activeConversationAnswer = String(answerText || "").trim();
}

function moveToolPanelsIntoWorkspace() {
  if (!contentColumn) return;
  [".timetable-panel", ".memory-panel", ".backup-panel", ".execution-panel"]
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
    "chat", "schedule", "timetable", "preferences", "backup", "weekly-planner",
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
  const isSchedule = activeWorkspaceView === "schedule";
  const isWeeklyPlanner = activeWorkspaceView === "weekly-planner";
  const isToolPage = ["timetable", "preferences", "backup"].includes(activeWorkspaceView);

  setPanelHidden(composerColumn, !isChat);
  setPanelHidden(composerPanel, !isChat);
  setPanelHidden(quickAccess, !isChat);
  setPanelHidden(conversationStream, !isChat);
  setPanelHidden(assistantPanel, !isChat);
  setPanelHidden(visualGrid, !isChat);
  setPanelHidden(document.querySelector(".adjustment-panel"), !isChat);
  setPanelHidden(schedulePanel, !isSchedule);
  setPanelHidden(agendaPanel, true);
  setPanelHidden(weeklyPanel, !isWeeklyPlanner);
  setPanelHidden(document.querySelector(".timetable-panel"), activeWorkspaceView !== "timetable");
  setPanelHidden(document.querySelector(".memory-panel"), activeWorkspaceView !== "preferences");
  setPanelHidden(document.querySelector(".backup-panel"), activeWorkspaceView !== "backup");
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
  return (lastAgendaData?.items || []).reduce((result, item) => {
    const date = agendaItemDate(item);
    (result[date] ||= []).push(item);
    return result;
  }, {});
}

function scheduleItemMarkup(item, compact = false) {
  return `
    <article class="schedule-event ${escapeHtml(item.kind || "task")}" title="${escapeHtml(item.title || "??")}">
      <time>${escapeHtml(timePart(item.start_at))}${compact ? "" : ` ? ${escapeHtml(timePart(item.end_at))}`}</time>
      <div><strong>${escapeHtml(item.title || "?????")}</strong>${compact ? "" : `<small>${escapeHtml(item.location_name || (item.kind === "travel" ? "????" : "????"))}</small>`}</div>
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
    schedulePeriodLabel.textContent = selected === today ? "??" : `${selected.slice(5).replace("-", "?")}?`;
    scheduleDayView.innerHTML = dayItems.length
      ? `<div class="schedule-day-timeline">${dayItems.map((item) => scheduleItemMarkup(item)).join("")}</div>`
      : `<div class="schedule-empty"><strong>?????????</strong><span>?????????????????????????????</span></div>`;
  }
  if (scheduleViewMode === "week") {
    const weekDates = Array.from({ length: 7 }, (_, index) => addWeeklyDays(startOfWeek, index));
    schedulePeriodLabel.textContent = `${startOfWeek.slice(5).replace("-", "?")}? ? ${weekDates[6].slice(5).replace("-", "?")}?`;
    scheduleWeekView.innerHTML = `<div class="schedule-week-grid">${weekDates.map((date) => {
      const items = (byDate[date] || []).sort((a, b) => new Date(a.start_at) - new Date(b.start_at));
      const dateValue = scheduleDateValue(date);
      const weekday = "???????"[dateValue.getUTCDay() === 0 ? 6 : dateValue.getUTCDay() - 1];
      return `<section class="schedule-week-day ${date === today ? "is-today" : ""}">
        <header><span>?${weekday}</span><strong>${date.slice(8)}<small>?</small></strong><em>${items.length ? `${items.length}?` : "??"}</em></header>
        <div>${items.length ? items.map((item) => scheduleItemMarkup(item, true)).join("") : `<p class="schedule-empty-mini">??????</p>`}</div>
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
      cells.push(`<button type="button" class="schedule-month-cell ${date === today ? "is-today" : ""} ${date === selected ? "is-selected" : ""}" data-schedule-date="${date}">
        <span>${day}</span><small>${items.length ? `${items.length}?` : ""}</small><i>${items.slice(0, 3).map((item) => `<b class="${escapeHtml(item.kind || "task")}"></b>`).join("")}</i>
      </button>`);
    }
    scheduleMonthView.innerHTML = `<div class="schedule-month-weekdays">${"???????".split("").map((day) => `<span>?${day}</span>`).join("")}</div><div class="schedule-month-grid">${cells.join("")}</div>`;
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
  if (scheduleState) scheduleState.textContent = `${dayItems.length} ???`;
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
  toolsToggle?.addEventListener("click", () => openDrawer(toolsSidebar, toolsToggle));
  historyClose?.addEventListener("click", closeDrawers);
  toolsClose?.addEventListener("click", closeDrawers);
  drawerBackdrop?.addEventListener("click", closeDrawers);

  newConversation?.addEventListener("click", () => {
    setActiveWorkspaceView("chat");
    setResultMode(false);
    clearConversationStream();
    queryInput.value = "";
    answer.textContent = "?????????????????????????????????????????????????????";
    answer.classList.add("muted");
    assistantActions.innerHTML = "";
    freshness.innerHTML = "";
    closeDrawers();
    queryInput.focus();
  });

  historyList?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-history-index]");
    if (!button) return;
    const items = readLocalSnapshot(conversationHistoryKey, [])
      .filter((item) => item && item.query)
      .slice(0, 24);
    const item = items[Number(button.dataset.historyIndex)];
    if (!item) return;
    setActiveWorkspaceView("chat");
    queryInput.value = item.query;
    restoreConversationSnapshot(item.query, item.answer);
    lastResultQuery = item.query;
    historyList.querySelectorAll(".history-item").forEach((historyButton) => {
      historyButton.classList.toggle("active", historyButton === button);
    });
    if (item.response?.plan) {
      renderResponse(item.response);
      closeDrawers();
      return;
    }
    setResultMode(false);
    answer.textContent = item.answer || "???????????????";
    answer.classList.toggle("muted", !item.answer);
    assistantActions.innerHTML = "";
    freshness.innerHTML = '<span class="source-tag">??????</span>';
    closeDrawers();
    assistantPanel?.scrollIntoView({ behavior: "smooth", block: "center" });
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

function memoryBackupItems(items) {
  return (items || []).slice(0, 100).map((item) => ({
    category: item.category,
    key: item.key,
    label: item.label,
    value: item.value,
    enabled: item.enabled !== false,
  }));
}

function timetableBackupValue(value) {
  if (!value?.entries?.length) return null;
  return {
    name: value.timetable?.name || "????",
    term_start: value.timetable?.term_start || null,
    term_end: value.timetable?.term_end || null,
    enabled: value.timetable?.enabled !== false,
    entries: value.entries.slice(0, 500).map((item) => ({
      course_name: item.course_name,
      weekday: item.weekday,
      start_period: item.start_period,
      end_period: item.end_period,
      location: item.location || null,
      weeks: item.weeks || [],
    })),
  };
}

function calendarBackupItems(items) {
  return (items || []).slice(0, 366).map((item) => ({
    date: item.date,
    action: item.action,
    replacement_weekday: item.replacement_weekday || null,
    label: item.label || "??????",
    source_ref: item.source_ref || null,
  }));
}

async function buildPersonalDataBackup() {
  const localMemories = readLocalSnapshot(memorySnapshotKey, []);
  const localTimetable = readLocalSnapshot(timetableSnapshotKey, null);
  const localCalendar = readLocalSnapshot(calendarSnapshotKey, []);
  const localPlan = readLocalSnapshot(planSnapshotKey, null);
  const query = new URLSearchParams({ thread_id: consoleThreadId });
  let server = null;
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/profile?${query}`,
    );
    if (response.ok) server = await response.json();
  } catch {
    // A local backup must still be available during a temporary server outage.
  }
  return {
    product: "yicheng-agent",
    schema_version: "1.0",
    exported_at: new Date().toISOString(),
    user_id: consoleUserId,
    thread_id: consoleThreadId,
    memories: localMemories.length
      ? memoryBackupItems(localMemories)
      : server?.memories || [],
    timetable: timetableBackupValue(localTimetable)
      || server?.timetable
      || null,
    calendar_overrides: localCalendar.length
      ? calendarBackupItems(localCalendar)
      : server?.calendar_overrides || [],
    reminder_settings: currentReminderSettings
      || readLocalSnapshot(reminderSettingsSnapshotKey, null)
      || server?.reminder_settings
      || null,
    current_plan: localPlan || server?.current_plan || null,
    client_state: {
      memory_snapshot: localMemories,
      timetable_snapshot: localTimetable,
      calendar_snapshot: localCalendar,
      plan_snapshot: localPlan,
      campus_snapshot: readLocalSnapshot(campusSnapshotKey, null),
      behavior_history: readLocalSnapshot(behaviorHistoryKey, []),
      suggestion_feedback: readLocalSnapshot(suggestionFeedbackKey, {}),
      personalization_enabled:
        localStorage.getItem(personalizationEnabledKey) === "true",
      shown_reminders: readLocalSnapshot(shownReminderKey, {}),
      reminder_settings_snapshot: readLocalSnapshot(
        reminderSettingsSnapshotKey,
        null,
      ),
    },
  };
}

function validatePersonalDataBackup(value) {
  if (!value || typeof value !== "object") {
    throw new Error("??????????????");
  }
  if (value.product !== "yicheng-agent" || value.schema_version !== "1.0") {
    throw new Error("?????????????????????????");
  }
  const identityPattern = /^[A-Za-z0-9_-]+$/;
  if (
    typeof value.user_id !== "string"
    || !identityPattern.test(value.user_id)
    || value.user_id.length > 64
    || typeof value.thread_id !== "string"
    || !identityPattern.test(value.thread_id)
    || value.thread_id.length > 128
  ) {
    throw new Error("??????????????");
  }
  if (!Array.isArray(value.memories) || value.memories.length > 100) {
    throw new Error("????????????????");
  }
  if (
    value.timetable
    && (
      !Array.isArray(value.timetable.entries)
      || value.timetable.entries.length > 500
    )
  ) {
    throw new Error("??????????????");
  }
  if (
    !Array.isArray(value.calendar_overrides)
    || value.calendar_overrides.length > 366
  ) {
    throw new Error("????????????????");
  }
  return value;
}

function personalDataSummary(value) {
  const courseCount = value.timetable?.entries?.length || 0;
  const calendarCount = value.calendar_overrides?.length || 0;
  const planLabel = value.current_plan ? "?1?????" : "";
  return (
    `??? ${value.memories.length} ??????${courseCount} ??????`
    + `${calendarCount} ?????${planLabel}?????????`
  );
}

profileExport.addEventListener("click", async () => {
  profileExport.disabled = true;
  profileExport.textContent = "?????????";
  profileBackupState.className = "storage-note";
  try {
    const backup = await buildPersonalDataBackup();
    const blob = new Blob(
      [JSON.stringify(backup, null, 2)],
      { type: "application/json;charset=utf-8" },
    );
    const link = document.createElement("a");
    const date = shanghaiDateString();
    link.href = URL.createObjectURL(blob);
    link.download = `????????_${date}.json`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    profileBackupState.textContent = (
      "??????????????????? API ?????????"
    );
    profileBackupState.classList.add("ready");
  } catch (error) {
    profileBackupState.textContent = (
      error instanceof Error ? error.message : "???????????"
    );
    profileBackupState.classList.add("error");
    renderDebug(error);
  } finally {
    profileExport.disabled = false;
    profileExport.textContent = "????????";
  }
});

profileImportFile.addEventListener("change", async () => {
  pendingProfileBackup = null;
  profileRestore.hidden = true;
  profileBackupState.className = "storage-note";
  const file = profileImportFile.files?.[0];
  if (!file) return;
  if (file.size > 2_000_000) {
    profileBackupState.textContent = "???????? 2 MB?";
    profileBackupState.classList.add("error");
    return;
  }
  try {
    const backup = validatePersonalDataBackup(
      JSON.parse(await file.text()),
    );
    pendingProfileBackup = backup;
    profileBackupState.textContent = personalDataSummary(backup);
    profileBackupState.classList.add("ready");
    profileRestore.hidden = false;
  } catch (error) {
    profileBackupState.textContent = (
      error instanceof Error ? error.message : "?????????"
    );
    profileBackupState.classList.add("error");
  }
});

profileRestore.addEventListener("click", async () => {
  if (!pendingProfileBackup) return;
  profileRestore.disabled = true;
  profileRestore.textContent = "?????????";
  profileBackupState.className = "storage-note";
  try {
    const backup = pendingProfileBackup;
    const response = await fetch(
      `/api/v1/users/${backup.user_id}/profile/restore`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(backup),
      },
    );
    const result = await response.json();
    if (!response.ok) throw result;

    localStorage.setItem("yicheng_user_id", backup.user_id);
    localStorage.setItem("yicheng_thread_id", backup.thread_id);
    const client = backup.client_state || {};
    writeLocalSnapshot(
      memorySnapshotKey,
      client.memory_snapshot?.length
        ? client.memory_snapshot
        : backup.memories,
    );
    writeLocalSnapshot(
      timetableSnapshotKey,
      client.timetable_snapshot
        || (
          backup.timetable
            ? {
                timetable: {
                  name: backup.timetable.name,
                  term_start: backup.timetable.term_start,
                  term_end: backup.timetable.term_end,
                  enabled: backup.timetable.enabled,
                },
                entries: backup.timetable.entries,
              }
            : null
        ),
    );
    writeLocalSnapshot(
      calendarSnapshotKey,
      client.calendar_snapshot?.length
        ? client.calendar_snapshot
        : backup.calendar_overrides,
    );
    writeLocalSnapshot(
      planSnapshotKey,
      client.plan_snapshot || backup.current_plan || null,
    );
    writeLocalSnapshot(
      campusSnapshotKey,
      client.campus_snapshot || null,
    );
    writeLocalSnapshot(
      behaviorHistoryKey,
      client.behavior_history || [],
    );
    writeLocalSnapshot(
      suggestionFeedbackKey,
      client.suggestion_feedback || {},
    );
    localStorage.setItem(
      personalizationEnabledKey,
      String(client.personalization_enabled === true),
    );
    writeLocalSnapshot(
      shownReminderKey,
      client.shown_reminders || {},
    );
    writeLocalSnapshot(
      reminderSettingsSnapshotKey,
      client.reminder_settings_snapshot
        || backup.reminder_settings
        || null,
    );
    profileBackupState.textContent = (
      `?????${result.memories_restored} ????`
      + `${result.timetable_entries_restored} ??????`
      + "??????????????"
    );
    profileBackupState.classList.add("ready");
    setTimeout(() => globalThis.location.reload(), 900);
  } catch (error) {
    profileBackupState.textContent = error?.error?.message
      || "??????????????????????";
    profileBackupState.classList.add("error");
    renderDebug(error);
  } finally {
    profileRestore.disabled = false;
    profileRestore.textContent = "?????????";
  }
});

function clientContextSnapshot() {
  const memories = readLocalSnapshot(memorySnapshotKey, []);
  const timetableData = readLocalSnapshot(timetableSnapshotKey, null);
  const calendarOverrides = readLocalSnapshot(calendarSnapshotKey, []);
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
        name: timetableData.timetable?.name || "????",
        term_start: timetableData.timetable?.term_start || null,
        term_end: timetableData.timetable?.term_end || null,
        enabled: timetableData.timetable?.enabled ?? true,
        entries: timetableData.entries,
      }
      : null,
    calendar_overrides: calendarOverrides.map((item) => ({
      date: item.date,
      action: item.action,
      replacement_weekday: item.replacement_weekday || null,
      label: item.label,
      source_ref: item.source_ref || null,
    })),
    previous_plan: previousPlan,
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
  };
}

function renderCampus(campus, { isDefault = false } = {}) {
  currentCampusProfile = campus;
  renderPersonalizationState();
  if (!campus) {
    campusState.textContent = "????";
    campusSummary.textContent = "????????????????????";
    campusSummary.classList.add("muted");
    campusReset.hidden = true;
    return;
  }
  const locationCount = campus.locations?.length
    ?? campus.location_count
    ?? 0;
  campusName.value = campus.display_name || "";
  campusCity.value = campus.search_city || "";
  campusState.textContent = isDefault ? "????" : "???";
  campusState.classList.add("ready");
  campusSummary.classList.remove("muted");
  campusSummary.innerHTML = `
    <strong>${escapeHtml(campus.display_name)}</strong>
    <span>??? ${locationCount} ?????${
      isDefault
        ? "????????????"
        : "???????????????????????????????"
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
    campusSummary.textContent = "??????????????????";
    campusSummary.classList.remove("muted");
    return;
  }
  campusDiscover.disabled = true;
  campusDiscover.textContent = "?????????";
  campusSummary.textContent = "???????????????????";
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
    campusState.textContent = "????";
    campusSummary.textContent = error?.error?.message
      || "???????????????????????";
    campusSummary.classList.remove("muted");
  } finally {
    campusDiscover.disabled = false;
    campusDiscover.textContent = "??????";
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

async function initializeAccess() {
  try {
    const response = await fetch("/api/v1/auth/status");
    const status = await response.json();
    if (!status.enabled) {
      accessGate.hidden = true;
      logoutButton.hidden = true;
      return true;
    }
    if (status.authenticated) {
      accessGate.hidden = true;
      logoutButton.hidden = false;
      return true;
    }
    localStorage.removeItem(accessTokenKey);
    loginUsername.value = status.test_username || "";
    loginPassword.value = "";
    loginMessage.textContent = status.configured
      ? "???????????????????"
      : "??????????????????????";
    accessGate.hidden = false;
    logoutButton.hidden = true;
    return false;
  } catch {
    accessGate.hidden = false;
    loginMessage.textContent = "???????????????????";
    return false;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginMessage.textContent = "?????????";
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: loginUsername.value.trim(),
      password: loginPassword.value,
    }),
  });
  const data = await response.json();
  if (!response.ok) {
    loginMessage.textContent = data?.error?.message || "???????";
    return;
  }
  localStorage.setItem(accessTokenKey, data.access_token);
  globalThis.location.reload();
});

logoutButton.addEventListener("click", () => {
  localStorage.removeItem(accessTokenKey);
  globalThis.location.reload();
});

const sourceLabels = {
  user: "????",
  live_api: "????",
  structured: "?????",
  demo_fixture: "????",
  cache: "????",
  estimated: "????",
  rag: "????",
  unknown: "????",
};

const memoryDefinitions = {
  buffer_min: {
    label: "??????",
    placeholder: "???15??",
    category: "preference",
  },
  walking_speed: {
    label: "????",
    placeholder: "??????",
    category: "preference",
  },
  transport_mode: {
    label: "??????",
    placeholder: "??????????",
    category: "preference",
  },
  avoid_congestion: {
    label: "??????",
    placeholder: "???",
    category: "preference",
  },
  avoid_rain: {
    label: "????",
    placeholder: "???",
    category: "preference",
  },
  avoid_tight_schedule: {
    label: "??????",
    placeholder: "???",
    category: "preference",
  },
  preferred_locations: {
    label: "????",
    placeholder: "??????????",
    category: "preference",
  },
  preferred_study_period: {
    label: "??????",
    placeholder: "????????",
    category: "habit",
  },
  preferred_study_location: {
    label: "??????",
    placeholder: "????????",
    category: "preference",
  },
  usual_bedtime: {
    label: "??????",
    placeholder: "???23:30",
    category: "habit",
  },
  usual_wake_time: {
    label: "??????",
    placeholder: "???07:00",
    category: "habit",
  },
  sleep_goal_hours: {
    label: "??????",
    placeholder: "???7.5??",
    category: "preference",
  },
  weekly_daily_focus_limit_min: {
    label: "????????",
    placeholder: "???180??",
    category: "preference",
  },
};

function behaviorTopic(title) {
  const definitions = [
    ["study", "??", ["??", "??", "??", "??"]],
    ["exercise", "??", ["??", "??", "??", "??"]],
    ["meal", "??", ["??", "??", "??", "??", "??"]],
    ["parcel", "???", ["??", "??", "??"]],
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
      if (!topic || item.reason === "?????????") return [];
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
      ? `?????? ${patterns.length} ?????????????????`
      : "?????????????????3??????????"
    : "??????????????????????????";
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
    "?????????????????????????"
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
  if (!value) return "?";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));
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
  clock.textContent = `???? ${formatted}`;
}

function renderTimeline(data) {
  const items = data.plan?.items || [];
  const locationNames = data.location_names || {};
  const changes = data.plan_diff || [];
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
        ? `${timePart(change.before_start)}?${timePart(change.before_end)}`
        : "???";
      const after = change.after_start
        ? `${timePart(change.after_start)}?${timePart(change.after_end)}`
        : "???";
      return `<span class="result-change-chip ${escapeHtml(change.change_type)}">
        <b>${escapeHtml(change.title)}</b>
        <em>${escapeHtml(change.summary)}</em>
        <small>${before} ? ${after}</small>
      </span>`;
    });
    if (travelDelta) {
      changeCards.push(`<span class="result-change-chip travel-change">
        <b>????</b>
        <em>${travelDelta < 0 ? "??" : "??"}${Math.abs(travelDelta)}??</em>
        <small>${previousTravel}?? ? ${currentTravel}??</small>
      </span>`);
    }
    if (waitingDelta) {
      const previousWaiting = planIdleMinutes(data.previous_plan);
      const currentWaiting = planIdleMinutes(data.plan);
      changeCards.push(`<span class="result-change-chip waiting-change">
        <b>????</b>
        <em>${waitingDelta < 0 ? "??" : "??"}${Math.abs(waitingDelta)}??</em>
        <small>${previousWaiting}?? ? ${currentWaiting}??</small>
      </span>`);
    }
    resultChangeSummary.innerHTML = changeCards.length
      ? `<strong>????</strong><div>${changeCards.join("")}</div>`
      : "";
    resultChangeSummary.hidden = changeCards.length === 0;
  }
  const pendingCount = (data.task_statuses || [])
    .filter((task) => task.status === "needs_adjustment").length;
  planTitle.textContent = pendingCount
    ? "???????"
    : "???????";
  timeline.classList.toggle("empty", items.length === 0);
  timeline.innerHTML = items.length
    ? items.map((item) => {
      const isTravel = item.item_type === "travel";
      const travelModeLabels = {
        walk: "????",
        bicycle: "?????",
        electrobike: "?????",
      };
      const title = isTravel
        ? travelModeLabels[item.travel_mode] || "??"
        : item.title;
      const location = item.location_id
        ? locationNames[item.location_id] || "?????"
        : "";
      const duration = Math.max(
        0,
        Math.round((new Date(item.end_at) - new Date(item.start_at)) / 60000),
      );
      const reason = isTravel
        ? item.congestion_delay_min > 0
          ? `${item.source === "live_api" ? "????" : "??????"} ${item.base_duration_min} ????????? ${item.congestion_delay_min} ??`
          : `?????????? ${duration} ??`
        : item.reason === "?????????"
          ? "????????????"
          : "????????????????";
      const itemIcon = isTravel
        ? "travel"
        : title.includes("???") || title.includes("??") || title.includes("??")
          ? "book"
          : title.includes("??") || title.includes("??")
            ? "package"
            : title.includes("??") || title.includes("??")
              ? "activity"
               : "calendar";
      const change = isTravel ? null : changesByTask.get(item.task_id);
      return `
        <div class="timeline-item ${isTravel ? "travel" : ""} ${change ? `has-change ${escapeHtml(change.change_type)}` : ""}">
          <div class="time">${timePart(item.start_at)}?${timePart(item.end_at)}</div>
          <div class="rail"><span></span></div>
          <div class="content">
            <span class="timeline-kind-icon">${dashboardIcon(itemIcon)}</span>
            <strong>${escapeHtml(title)}</strong>
            ${change ? `<span class="timeline-change-badge">${escapeHtml(change.summary)}</span>` : ""}
            ${location ? `<small>${escapeHtml(location)}</small>` : ""}
            ${change?.before_start ? `<small class="timeline-before-time">??? ${timePart(change.before_start)}?${timePart(change.before_end)}</small>` : ""}
            <p>${escapeHtml(reason)}</p>
          </div>
        </div>`;
    }).join("")
    : "??????????";
}

function setResultMode(active) {
  const wasActive = document.body.classList.contains("has-plan-result");
  document.body.classList.toggle("has-plan-result", active);
  if (!active) return;
  setActiveWorkspaceView("chat");
  if (wasActive) return;
  requestAnimationFrame(() => {
    globalThis.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function setInlineRequestEditing(active) {
  resultRequest.classList.toggle("is-editing", active);
  resultRequestText.hidden = active;
  resultRequestInput.hidden = !active;
  resultEdit.textContent = active ? "????" : "????";
  resultRerun.textContent = active ? "??????" : "????";
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
  const endTimes = (plan.items || []).map((item) => new Date(item.end_at).getTime());
  const finalEnd = endTimes.length
    ? timePart(new Date(Math.max(...endTimes)))
    : "?";
  const feasible = plan.status === "valid" && scheduled === requested;
  const cards = [
    [
      feasible ? "???" : "???",
      feasible ? "????????" : "???????",
      feasible ? "success" : "attention",
      "feasibility",
    ],
    [
      `${scheduled}/${requested}`,
      "?????",
      scheduled === requested ? "success" : "attention",
      "tasks",
    ],
    [finalEnd, "??????", "time", "end"],
    [`${metrics.buffer_minutes || 0}??`, "????", "time", "buffer"],
    [`${metrics.travel_minutes || 0}??`, "????", "time", "travel"],
    [
      `${passed}/${checks.length}`,
      "??????",
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
  const query = lastResultQuery || activeConversationQuery || "????????";
  resultRequestText.textContent = query;
  setInlineRequestEditing(false);
  resultRequest.hidden = false;

  const checks = data.constraint_checks || [];
  const passed = checks.filter((item) => item.passed).length;
  resultConstraintTotal.textContent = `${passed}/${checks.length} ??`;
  resultConstraints.innerHTML = checks.length
    ? checks.map((check) => `
      <div class="result-check-item ${check.passed ? "passed" : "failed"}">
        <span>${check.passed ? dashboardIcon("feasibility") : "!"}</span>
        <div>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.message)}</small>
        </div>
        <em>${check.passed ? "??" : "??"}</em>
      </div>
    `).join("")
    : '<p class="result-detail-empty">???????</p>';

  const freshness = data.data_freshness || {};
  const isLive = (value) => value === "live_api";
  const sourceEntries = [
    {
      icon: "map",
      name: "????",
      purpose: isLive(freshness.route)
        ? "?????????"
        : "??? ? ????????",
      state: isLive(freshness.route) ? "??" : "??",
    },
    {
      icon: "building",
      name: "????",
      purpose: "????????",
      state: "???",
    },
    {
      icon: "cloud",
      name: "????",
      purpose: isLive(freshness.weather)
        ? "?????????"
        : "????????",
      state: isLive(freshness.weather) ? "??" : "??",
    },
    {
      icon: "calendar",
      name: "????",
      purpose: "?????????",
      state: "????",
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
      <strong>?????</strong>
      <span>??? ${scheduledCount}/${statuses.length}${
        pendingCount ? ` ? ${pendingCount}????` : ""
      }</span>
    </div>
    ${statuses.map((task) => {
      const pending = task.status === "needs_adjustment";
      const location = task.location_id
        ? ` ? ${escapeHtml(
          locationNames[task.location_id] || "?????"
        )}`
        : "";
      return `
        <div class="task-status-item ${
          pending ? "needs-adjustment" : "scheduled"
        }">
          <span class="task-status-icon">${pending ? "!" : "?"}</span>
          <div>
            <strong>${escapeHtml(task.title)}</strong>
            <small>${task.duration_min}??${location} ? ${
              escapeHtml(task.message)
            }</small>
          </div>
          <span class="task-status-badge">${
            pending ? "???" : "???"
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
          step.status === "success" ? "??"
            : step.status === "fallback" ? "????"
              : step.status === "failed" ? "???" : "??"
        }</span>
      </div>`).join("")
    : "????????????";
}

function renderConstraints(checks = []) {
  constraints.classList.toggle("empty", checks.length === 0);
  constraints.innerHTML = checks.length
    ? checks.map((check) => `
      <div class="check-item ${check.passed ? "passed" : "failed"}">
        <span class="check-icon">${check.passed ? "?" : "!"}</span>
        <div>
          <strong>${escapeHtml(check.label)}</strong>
          <small>${escapeHtml(check.message)}</small>
        </div>
      </div>`).join("")
    : "??????????";
}

function renderDiff(data) {
  const changes = data.plan_diff || [];
  const hasChanges = changes.length > 0 || Boolean(data.adjustment_reason);
  adjustmentPanel.classList.toggle("has-changes", hasChanges);
  adjustment.textContent = data.adjustment_reason || "?????????";
  adjustment.classList.toggle("muted", !data.adjustment_reason);
  diff.innerHTML = changes.map((change) => `
    <div class="diff-item">
      <div>
        <strong>${escapeHtml(change.title)}</strong>
        <span>${escapeHtml(change.summary)}</span>
      </div>
      <small>
        ${change.before_start ? `${timePart(change.before_start)}?${timePart(change.before_end)}` : "???"}
        <b>?</b>
        ${change.after_start ? `${timePart(change.after_start)}?${timePart(change.after_end)}` : "???"}
      </small>
    </div>`).join("");
}

function renderEvidence(data) {
  const sourceEntries = Object.entries(data.data_freshness || {});
  const sourceNames = { route: "??", weather: "??", knowledge: "??" };
  freshness.innerHTML = sourceEntries.map(([key, value]) => `
    <span class="tag">${sourceNames[key] || key} ? ${sourceLabels[value] || value}</span>
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
        && item.message?.includes("???????")
      )
    ),
  );
  const careInsights = (data.insights || []).filter(
    (item) => ["required", "attention"].includes(item.importance)
      && !["??????", "?????????"].includes(item.title),
  );
  const careItems = [
    ...warningItems.map((item) => ({
      title: item.severity === "error" ? "???" : "????",
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
    : "???????";
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
    : "??????????????";
}

function renderDebug(payload) {
  lastDebugPayload = payload;
  debugContent.textContent = payload
    ? JSON.stringify(payload, null, 2)
    : "???????";
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
          ????
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

function renderResponse(data) {
  const shouldStayInDashboard = document.body.classList.contains(
    "has-plan-result",
  );
  lastResultData = data;
  if (resultActionStatus) resultActionStatus.hidden = true;
  if (data.current_plan_saved && data.plan?.status === "valid") {
    writeLocalSnapshot(planSnapshotKey, data.plan);
  }
  recordBehaviorHistory(data);
  answer.textContent = data.answer;
  answer.classList.remove("muted");
  completeConversationTurn(data.answer);
  saveState.textContent = data.current_plan_saved
    ? "???????"
    : data.plan ? "?????????" : "????????";
  saveState.classList.toggle("saved", data.current_plan_saved);
  renderTimeline(data);
  renderResultSummary(data);
  renderResultDashboard(data);
  renderTaskStatuses(data.task_statuses, data.location_names);
  renderExecution(data.execution_steps);
  renderConstraints(data.constraint_checks);
  renderDiff(data);
  renderEvidence(data);
  renderInsights(data.insights || []);
  renderSuggestedActions(data.suggested_actions);
  renderDebug(data);
  if (data.plan) {
    setResultMode(true);
  } else if (shouldStayInDashboard) {
    resultRequestText.textContent = lastResultQuery;
    setInlineRequestEditing(false);
    resultRequest.hidden = false;
    resultDetails.hidden = true;
    planTitle.textContent = "??????";
    timeline.className = "timeline empty";
    timeline.textContent = data.answer || "???????????";
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
  course: "????",
  plan: "????",
  weekly: "???",
  manual: "????",
};

function agendaItemDate(item) {
  return shanghaiDateString(new Date(item.start_at));
}

function renderAgenda(data, selectedDate) {
  const items = (data.items || []).filter(
    (item) => agendaItemDate(item) === selectedDate,
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
    ? `?? ? ${items.length}?`
    : `${selectedDate.slice(5).replace("-", "?")}? ? ${items.length}?`;
  agendaState.classList.toggle("ready", items.length > 0);
  agendaMetrics.innerHTML = `
    <span>?? ${courseCount} ???</span>
    <span>??? ${Math.round(dayBusy / 6) / 10} ??</span>
    <span>?? ${reminderCount} ?</span>
    <span>?????7?</span>
  `;
  agendaList.classList.toggle("muted", items.length === 0);
  agendaList.innerHTML = items.length
    ? items.map((item) => `
      <div class="agenda-item ${escapeHtml(item.kind)}">
        <time>${escapeHtml(timePart(item.start_at))}
          ?${escapeHtml(timePart(item.end_at))}</time>
        <span class="agenda-kind" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${item.location_name
            ? escapeHtml(item.location_name)
            : item.kind === "travel"
              ? "???????"
              : "?????"}${
            item.locked ? " ? ????" : ""
          }</small>
        </div>
        <span class="agenda-source">${
          agendaSourceLabels[item.source] || "????"
        }</span>
      </div>
    `).join("")
    : `
      <div class="weekly-safe">
        <strong>??????????</strong>
        <span>????????????????????????????????</span>
      </div>
    `;
  agendaReminders.innerHTML = dayReminders.length
    ? `
      <div class="agenda-reminder-heading">
        <strong>????????</strong>
        <span>?????????????????</span>
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
        <strong>??7??????</strong>
        <span>???????????????</span>
      </div>
      ${careItems.map((item, index) => `
      <div class="care-card ${escapeHtml(item.level)}">
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.content)}</p>
        ${item.action_query ? `
          <button class="ghost" data-care-action="${index}">
            ?????????
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
  agendaState.textContent = "????";
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
      "????????????????????"
      + "????????????????????"
    );
    reminderEnable.textContent = "????????";
    reminderEnable.disabled = true;
    startReminderPolling();
  } else if (permission === "denied") {
    reminderState.textContent = (
      "??????????????????????????"
      + "???????????"
    );
    reminderEnable.textContent = "????????";
    reminderEnable.disabled = true;
  } else if (permission === "unsupported") {
    reminderState.textContent = (
      "??????????????????????????"
    );
    reminderEnable.disabled = true;
  } else {
    reminderState.textContent = (
      "?????????????????????????"
    );
    reminderEnable.textContent = "???????";
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
      "????????????????????"
      + "???????????????"
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
    reminderState.textContent = "?????????";
  } catch (error) {
    reminderState.textContent = error?.error?.message
      || "?????????????";
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
      "?????????????????????????????"
    );
  }
});

agendaExport.addEventListener("click", async (event) => {
  event.preventDefault();
  const startDate = agendaDate.value || shanghaiDateString();
  const endDate = addWeeklyDays(startDate, 90);
  agendaExport.textContent = "?????????";
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
    link.download = `????????_${startDate}.ics`;
    link.click();
    URL.revokeObjectURL(url);
    reminderState.textContent = (
      "??????????????????????????????"
    );
  } catch (error) {
    reminderState.textContent = error?.error?.message
      || "?????????????";
    renderDebug(error);
  } finally {
    agendaExport.textContent = "????????????";
  }
});

function renderError(error) {
  const body = error?.error || {};
  answer.textContent = body.message || "???????????";
  answer.classList.remove("muted");
  completeConversationTurn(answer.textContent);
  warnings.innerHTML = `
    <div class="warning error">
      <strong>?????</strong>
      <span>????????????????????????????</span>
    </div>`;
  renderDebug(error);
}

function setLoading(active) {
  submitButton.disabled = active;
  resetButton.disabled = active;
  submitButton.textContent = active ? "???????" : "???????";
}

async function runRequest(url, options = {}, transformData = null) {
  setLoading(true);
  try {
    const response = await fetch(url, options);
    let data = await response.json();
    if (!response.ok) throw data;
    if (transformData) data = transformData(data);
    renderResponse(data);
    return data;
  } catch (error) {
    renderError(error);
    throw error;
  } finally {
    setLoading(false);
  }
}

async function submitQuery(rawQuery, { keepResultMode = false } = {}) {
  let query = rawQuery.trim();
  if (!query) {
    answer.textContent = "???????????????";
    return;
  }
  const choice = query.match(/^?\s*([12])$/);
  if (choice) {
    const action = lastSuggestedActions[Number(choice[1]) - 1];
    if (action) {
      query = action.query;
      queryInput.value = action.query;
    }
  }
  beginConversationTurn(query, { keepResultMode });
  queryInput.value = "";
  const data = await runRequest("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: consoleUserId,
      thread_id: consoleThreadId,
      query,
      mode: modeSelect.value,
      client_context: clientContextSnapshot(),
    }),
  }).catch(() => null);
  if (data) recordConversationHistory(query, data.answer, data);
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
  resultRerun.textContent = "???????";
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

resultRequestInput?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  resultRerun.click();
});

const resultActionQueries = {
  alternative: "??????????????????????????????????",
  travel: "??????????????????????????????",
  waiting: "?????????????????????????",
  order: "????????????????????",
};

function planFingerprint(data) {
  return (data?.plan?.items || []).map((item) => [
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
  if (!resultActionStatus || !after?.plan) return;
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
        alternative: "??????????????????????",
        travel: travelSaved
          ? `???????????? ${travelSaved} ???`
          : "????????????????????",
        waiting: waitingSaved
          ? `???????????????? ${waitingSaved} ???`
          : "?????????????????????",
        order: "???????????????????????",
      }
    : {
        alternative: "??????????????????????????",
        travel: "????????????????????????",
        waiting: "?????????????????????????",
        order: "??????????????????????????",
      };
  resultActionStatus.textContent = messages[action] || "????????";
  resultActionStatus.classList.toggle("is-unchanged", !changed);
  resultActionStatus.hidden = false;
}

function currentBaseRequirement() {
  const value = resultRequestText.textContent.trim() || lastResultQuery;
  return value.split(/\n?????/u, 1)[0].trim();
}

resultQuickActions?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-result-action]");
  if (!button || submitButton.disabled) return;
  const adjustment = resultActionQueries[button.dataset.resultAction];
  if (!adjustment) return;
  const action = button.dataset.resultAction;
  const before = lastResultData;
  const currentRequirement = currentBaseRequirement();
  const query = `${currentRequirement}\n?????${adjustment}`;
  resultQuickActions.querySelectorAll("button").forEach((item) => {
    item.disabled = true;
    item.classList.toggle("active", item === button);
  });
  try {
    const data = await submitQuery(query, { keepResultMode: true });
    if (data) renderResultActionOutcome(action, before, data);
  } finally {
    resultQuickActions.querySelectorAll("button").forEach((item) => {
      item.disabled = false;
    });
  }
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
    timeline.textContent = "??????????????";
    resultSummary.innerHTML = "";
    resultSummary.hidden = true;
    resultRequest.hidden = true;
    resultDetails.hidden = true;
    setResultMode(false);
    planTitle.textContent = "?????";
    taskStatuses.innerHTML = "";
    execution.className = "execution-list empty";
    execution.textContent = "????????????";
    constraints.className = "check-list empty";
    constraints.textContent = "??????????";
    diff.innerHTML = "";
    adjustmentPanel.classList.remove("has-changes");
    adjustment.textContent = "?????????";
    answer.textContent = data.message;
    answer.classList.remove("muted");
    warnings.textContent = "???????";
    warnings.className = "warnings muted";
    freshness.innerHTML = "";
    renderSuggestedActions([]);
    renderInsights([]);
    renderDebug(null);
    localStorage.removeItem(planSnapshotKey);
    saveState.textContent = "????????";
    saveState.classList.remove("saved");
  } catch (error) {
    renderError(error);
  } finally {
    setLoading(false);
  }
});

async function loadDemos({ autoRun = false } = {}) {
  const response = await fetch("/api/v1/demos");
  const demos = await response.json();
  const demoMarkup = demos.map((demo, index) => `
    <button data-demo="${escapeHtml(demo.id)}">
      <span class="demo-play" aria-hidden="true">?</span>
      <span>${escapeHtml(demo.title)}</span>
      <small>??${"????"[index] || index + 1}</small>
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
    if (data) recordConversationHistory(demo.query, data.answer, data);
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
  if (autoRun && demos.length) {
    await runDemo(demoButtons.querySelector("button"), demos[0]);
  }
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
  const weekday = "???????"[value.getUTCDay()];
  return `${month}?${day}? ? ?${weekday}`;
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
  library: "???",
  library_floor_6_12: "?????????",
  library_floor_7_11: "????????",
  teaching_building_6: "?????",
  parcel_station: "????",
  sf_express: "?????",
  jd_express: "?????",
  canteen: "????",
  track: "???",
  gym_south_track: "?????????",
  northwest_track: "?????",
  gym_main: "?????",
  gym_comprehensive: "???",
  laboratory: "???",
  student_dormitory: "????",
  campus_hospital: "???",
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
    valid: "?????",
    at_risk: "??????",
    infeasible: "????",
  };
  weeklyState.textContent = statusLabels[plan.status] || "???";
  weeklyState.classList.toggle("ready", plan.status === "valid");
  weeklySummary.classList.remove("muted");
  weeklySummary.innerHTML = `
    <strong>${escapeHtml(data.answer)}</strong>
    <div class="weekly-metrics">
      <span>?? ${plan.goals.length} ?</span>
      <span>??? ${plan.allocations.length} ?</span>
      <span>??? ${Math.round(plan.metrics.allocated_duration_min / 6) / 10} ??</span>
      <span>??? ${plan.metrics.unallocated_duration_min} ??</span>
    </div>
    ${capacitySummary.source === "personal_context" ? `
      <div class="weekly-context">
        <span>${capacitySummary.timetable_applied
          ? `??? ${capacitySummary.excluded_course_count || 0} ?????`
          : "????????"}</span>
        ${(capacitySummary.memory_labels || []).map((label) =>
          `<span>???${escapeHtml(label)}</span>`,
        ).join("")}
      </div>
      <p class="weekly-context-note">${escapeHtml(
        (capacitySummary.notes || []).join("?"),
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
          )} ??</small>
        </header>
        <div>
          ${items.length ? items.map((item) => {
            const goal = goals.get(item.goal_id);
            const stage = stages.get(item.stage_id);
            const locationLabel = weeklyLocationLabel(item.location_id);
            return `
              <article class="weekly-block">
                <time>${escapeHtml(weeklyTimeLabel(item.earliest_start))}
                  ? ${escapeHtml(weeklyTimeLabel(item.latest_end))}</time>
                <strong>${escapeHtml(stage?.title || goal?.title || "????")}</strong>
                <small>${escapeHtml(goal?.title || "")}${
                  locationLabel
                    ? ` ? ${escapeHtml(locationLabel)}`
                    : ""
                }</small>
              </article>
            `;
          }).join("") : "<p>????????????</p>"}
        </div>
      </section>
    `;
  }).join("");
  weeklyRisks.innerHTML = plan.issues.length
    ? plan.issues.map((issue) => `
      <div class="warning ${issue.severity === "error" ? "error" : ""}">
        <strong>????</strong>
        <span>${escapeHtml(issue.message)}</span>
      </div>
    `).join("")
    : `
      <div class="weekly-safe">
        <strong>????????</strong>
        <span>??????????????????????????</span>
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
      weeklyState.textContent = "?????";
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
        weeklyState.textContent = "????";
        weeklySummary.textContent = error?.error?.message
          || "??????????????????";
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
    weeklySummary.textContent = "????????????????";
    weeklySummary.classList.remove("muted");
    weeklyQuery.focus();
    return;
  }
  if (!weeklyStart.value) weeklyStart.value = nextWeeklyMonday();
  weeklyGenerate.disabled = true;
  weeklyState.textContent = "???????";
  weeklySummary.textContent = (
    "??????????????????????????????"
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
    weeklyGenerate.textContent = "??????????";
  } catch (error) {
    const questions = (error?.error?.details || [])
      .map((item) => item.question)
      .filter(Boolean);
    weeklyState.textContent = questions.length ? "????" : "????";
    weeklySummary.innerHTML = questions.length
      ? `
        <strong>${escapeHtml(error?.error?.message || "??????????")}</strong>
        <ul>${questions.map((item) =>
          `<li>${escapeHtml(item)}</li>`,
        ).join("")}</ul>
      `
      : escapeHtml(
        error?.error?.message
          || "???????????????????",
      );
    weeklySummary.classList.remove("muted");
    renderDebug(error);
  } finally {
    weeklyGenerate.disabled = false;
  }
});

function parseMemoryValue(key, rawValue) {
  const value = rawValue.trim();
  if (!value) throw new Error("???????????");
  if (key === "buffer_min") {
    const minutes = Number(value.match(/\d+/)?.[0]);
    if (!Number.isFinite(minutes) || minutes < 0 || minutes > 60) {
      throw new Error("???????0?60???");
    }
    return minutes;
  }
  if (key === "walking_speed") {
    const normalized = { ?: "slow", ??: "normal", ?: "fast" }[value];
    if (!normalized) throw new Error("???????????????");
    return normalized;
  }
  if (key === "transport_mode") {
    const normalized = {
      ??: "walk",
      ???: "bicycle",
      ??: "bicycle",
      ???: "electrobike",
      ???: "electrobike",
    }[value];
    if (!normalized) {
      throw new Error("?????????????????????");
    }
    return normalized;
  }
  if (["avoid_rain", "avoid_tight_schedule", "avoid_congestion"].includes(key)) {
    if (["?", "??", "??", "true"].includes(value.toLowerCase())) return true;
    if (["?", "???", "??", "false"].includes(value.toLowerCase())) return false;
    throw new Error("??????????????");
  }
  if (key === "preferred_locations") {
    return value.split(/[?,?]/).map((item) => item.trim()).filter(Boolean);
  }
  if (key === "preferred_study_period") {
    const normalized = {
      ??: "morning",
      ??: "morning",
      ??: "afternoon",
      ??: "evening",
      ??: "evening",
    }[value];
    if (!normalized) throw new Error("???????????????????");
    return normalized;
  }
  if (key === "weekly_daily_focus_limit_min") {
    const minutes = Number(value.match(/\d+/)?.[0]);
    if (!Number.isFinite(minutes) || minutes < 30 || minutes > 720) {
      throw new Error("???????????30?720???");
    }
    return minutes;
  }
  if (["usual_bedtime", "usual_wake_time"].includes(key)) {
    const matched = value.match(/^([01]?\d|2[0-3])[:?]([0-5]\d)$/);
    if (!matched) {
      throw new Error("??24?????????23:30?07:00?");
    }
    return `${matched[1].padStart(2, "0")}:${matched[2]}`;
  }
  if (key === "sleep_goal_hours") {
    const hours = Number(value.match(/\d+(?:\.\d+)?/)?.[0]);
    if (!Number.isFinite(hours) || hours < 4 || hours > 12) {
      throw new Error("?????????4?12???");
    }
    return hours;
  }
  return value;
}

function displayMemoryValue(key, value) {
  if (key === "buffer_min") return `${value}??`;
  if (key === "walking_speed") {
    return { slow: "?", normal: "??", fast: "?" }[value] || value;
  }
  if (key === "transport_mode") {
    return {
      walk: "??",
      bicycle: "???",
      electrobike: "???",
    }[value] || value;
  }
  if (["avoid_rain", "avoid_tight_schedule", "avoid_congestion"].includes(key)) {
    return value ? "?" : "?";
  }
  if (key === "preferred_study_period") {
    return {
      morning: "??",
      afternoon: "??",
      evening: "??",
    }[value] || value;
  }
  if (key === "weekly_daily_focus_limit_min") return `${value}??`;
  if (["usual_bedtime", "usual_wake_time"].includes(key)) return value;
  if (key === "sleep_goal_hours") return `${value}??`;
  if (Array.isArray(value)) return value.join("?");
  return String(value);
}

function updateMemoryPlaceholder() {
  const definition = memoryDefinitions[memoryType.value];
  memoryValue.placeholder = definition?.placeholder || "????";
}

async function loadMemories() {
  const response = await fetch(`/api/v1/users/${consoleUserId}/memories`);
  const data = await response.json();
  if (!response.ok) throw data;
  let items = data.items || [];
  const localItems = readLocalSnapshot(memorySnapshotKey, []);
  if (items.length) {
    writeLocalSnapshot(memorySnapshotKey, items);
  } else if (localItems.length) {
    items = localItems;
  }
  memoryList.classList.toggle("muted", items.length === 0);
  memoryList.innerHTML = items.length
    ? items.map((item) => `
      <div class="memory-item ${item.enabled ? "" : "disabled"}">
        <div>
          <strong>${escapeHtml(item.label)}</strong>
          <small>${escapeHtml(displayMemoryValue(item.key, item.value))}</small>
        </div>
        <div class="memory-actions">
          <button data-memory-edit="${escapeHtml(item.id)}">??</button>
          <button data-memory-toggle="${escapeHtml(item.id)}">
            ${item.enabled ? "??" : "??"}
          </button>
          <button class="danger-link" data-memory-delete="${escapeHtml(item.id)}">
            ??
          </button>
        </div>
      </div>
    `).join("")
    : "??????????";
  memoryList.querySelectorAll("[data-memory-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items.find((value) => value.id === button.dataset.memoryEdit);
      if (!item) return;
      memoryType.value = item.key in memoryDefinitions ? item.key : "custom_note";
      memoryValue.value = displayMemoryValue(item.key, item.value);
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

memoryType.addEventListener("change", updateMemoryPlaceholder);
memorySave.addEventListener("click", async () => {
  const definition = memoryDefinitions[memoryType.value];
  try {
    const parsedValue = parseMemoryValue(memoryType.value, memoryValue.value);
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
    await loadMemories();
    await loadAgenda(agendaDate.value || shanghaiDateString());
  } catch (error) {
    const message = error instanceof Error
      ? error.message
      : error?.error?.message || "?????????????";
    memoryList.textContent = message;
    memoryList.classList.remove("muted");
    renderDebug(error);
  }
});

function timetableWeekdayLabel(value) {
  return `?${"???????"[Number(value) - 1] || value}`;
}

async function fileToImportPayload(file) {
  const extension = file.name.split(".").pop().toLowerCase();
  if (extension === "xlsx" || extension === "pdf") {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return {
      format: extension === "pdf" ? "pdf_base64" : "xlsx_base64",
      content: btoa(binary),
    };
  }
  if (extension === "csv" || extension === "json") {
    return { format: extension, content: await file.text() };
  }
  throw new Error("??? .pdf?.xlsx?.csv ? .json ?????");
}

function renderTimetable(data) {
  const entries = data.entries || [];
  const isPreview = Boolean(entries.length && !data.timetable?.id);
  timetableSummary.classList.toggle("muted", entries.length === 0);
  timetableClear.hidden = entries.length === 0 || isPreview;
  if (!entries.length) {
    timetableSummary.textContent = "????????????";
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
  timetableSummary.innerHTML = `
    <div class="timetable-status">
      <strong>${escapeHtml(data.timetable?.name || "????")}</strong>
      <span>${entries.length}????? ? ${
        isPreview ? "????" : "???"
      }</span>
    </div>
    ${[...grouped.entries()].map(([weekday, values]) => `
      <div class="timetable-day">
        <strong>${timetableWeekdayLabel(weekday)}</strong>
        <div>
          ${values.map((entry) => `
            <span>${escapeHtml(entry.course_name)} ? ?${entry.start_period}${
              entry.end_period === entry.start_period
                ? ""
                : `?${entry.end_period}`
            }?${entry.location ? ` ? ${escapeHtml(entry.location)}` : ""}${
              entry.weeks?.length
                ? ` ? ?${escapeHtml(entry.weeks.join("?"))}?`
                : ""
            }</span>
          `).join("")}
        </div>
      </div>
    `).join("")}
  `;
}

async function loadTimetable() {
  const response = await fetch(`/api/v1/users/${consoleUserId}/timetable`);
  const data = await response.json();
  if (!response.ok) throw data;
  const timetableData = data.entries?.length
    ? data
    : readLocalSnapshot(timetableSnapshotKey, data);
  if (data.entries?.length) {
    writeLocalSnapshot(timetableSnapshotKey, data);
  }
  timetableName.value = timetableData.timetable?.name || "????";
  termStart.value = timetableData.timetable?.term_start || "";
  termEnd.value = timetableData.timetable?.term_end || "";
  renderTimetable(timetableData);
}

timetableImport.addEventListener("click", async () => {
  const file = timetableFile.files?.[0];
  if (!file) {
    timetableSummary.textContent = "???????????";
    timetableSummary.classList.remove("muted");
    return;
  }
  if (!termStart.value) {
    timetableSummary.textContent = (
      "????????????????????????????"
      + "??????????"
    );
    timetableSummary.classList.remove("muted");
    termStart.focus();
    return;
  }
  timetableImport.disabled = true;
  timetableImport.textContent = "???????";
  try {
    const filePayload = await fileToImportPayload(file);
    const importPayload = {
      name: timetableName.value.trim() || "????",
      term_start: termStart.value || null,
      term_end: termEnd.value || null,
      ...filePayload,
    };
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/timetable/preview`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(importPayload),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    pendingTimetableImport = importPayload;
    if (!termEnd.value && data.term_end) termEnd.value = data.term_end;
    renderTimetable({
      timetable: {
        name: importPayload.name,
        term_start: data.term_start,
        term_end: data.term_end,
      },
      entries: data.entries,
    });
    timetableConfirm.hidden = false;
    answer.textContent = (
      `?????? ${data.imported_count} ??????????????`
      + "????????????????????????????"
    );
    answer.classList.remove("muted");
  } catch (error) {
    timetableSummary.textContent = error instanceof Error
      ? error.message
      : error?.error?.message || "???????????";
    timetableSummary.classList.remove("muted");
    renderDebug(error);
  } finally {
    timetableImport.disabled = false;
    timetableImport.textContent = "???????";
  }
});

timetableFile.addEventListener("change", () => {
  pendingTimetableImport = null;
  timetableConfirm.hidden = true;
});

timetableConfirm.addEventListener("click", async () => {
  if (!pendingTimetableImport) return;
  timetableConfirm.disabled = true;
  timetableConfirm.textContent = "???????";
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/timetable/import`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pendingTimetableImport),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    writeLocalSnapshot(timetableSnapshotKey, data);
    renderTimetable(data);
    pendingTimetableImport = null;
    timetableConfirm.hidden = true;
    timetableFile.value = "";
    answer.textContent = (
      `?????????? ${data.imported_count} ??????`
      + "???????????????????????????"
    );
    answer.classList.remove("muted");
    await loadAgenda(agendaDate.value || shanghaiDateString());
  } catch (error) {
    timetableSummary.textContent = error?.error?.message
      || "???????????";
    timetableSummary.classList.remove("muted");
    renderDebug(error);
  } finally {
    timetableConfirm.disabled = false;
    timetableConfirm.textContent = "????????";
  }
});

timetableClear.addEventListener("click", async () => {
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/timetable`,
    { method: "DELETE" },
  );
  if (response.ok) {
    localStorage.removeItem(timetableSnapshotKey);
    renderTimetable({ timetable: null, entries: [] });
    await loadAgenda(agendaDate.value || shanghaiDateString());
  }
});

const calendarActionLabels = {
  no_class: "???",
  normal: "?????",
  makeup: "??",
};

function renderCalendarOverrides(items) {
  calendarList.classList.toggle("muted", !items.length);
  if (!items.length) {
    calendarList.textContent = "?????????";
    return;
  }
  calendarList.innerHTML = items.map((item) => {
    const weekday = item.replacement_weekday
      ? ` ? ??${"???????"[item.replacement_weekday - 1]}??`
      : "";
    return `
      <div class="calendar-item">
        <span>
          <strong>${escapeHtml(item.date)}</strong> ?
          ${calendarActionLabels[item.action] || escapeHtml(item.action)}
          ${weekday}<br />
          ${escapeHtml(item.label || "??????")}
        </span>
        <button type="button" data-calendar-delete="${escapeHtml(item.date)}">
          ??
        </button>
      </div>
    `;
  }).join("");
}

async function loadCalendarOverrides() {
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/calendar-overrides`,
  );
  const data = await response.json();
  if (!response.ok) throw data;
  const items = data.items?.length
    ? data.items
    : readLocalSnapshot(calendarSnapshotKey, []);
  if (data.items?.length) {
    writeLocalSnapshot(calendarSnapshotKey, data.items);
  }
  renderCalendarOverrides(items);
}

calendarAction.addEventListener("change", () => {
  calendarWeekday.hidden = calendarAction.value !== "makeup";
});

calendarSave.addEventListener("click", async () => {
  if (!calendarDate.value) {
    calendarList.textContent = "????????????";
    calendarList.classList.remove("muted");
    calendarDate.focus();
    return;
  }
  const payload = {
    date: calendarDate.value,
    action: calendarAction.value,
    replacement_weekday: calendarAction.value === "makeup"
      ? Number(calendarWeekday.value)
      : null,
    label: calendarLabel.value.trim() || "??????",
  };
  calendarSave.disabled = true;
  try {
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/calendar-overrides`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    const current = readLocalSnapshot(calendarSnapshotKey, []);
    const items = [
      data,
      ...current.filter((item) => item.date !== data.date),
    ].sort((left, right) => left.date.localeCompare(right.date));
    writeLocalSnapshot(calendarSnapshotKey, items);
    renderCalendarOverrides(items);
    calendarLabel.value = "";
    answer.textContent = (
      `??? ${data.date} ???????????????`
      + "???????????????????????"
    );
    answer.classList.remove("muted");
    await loadAgenda(agendaDate.value || shanghaiDateString());
  } catch (error) {
    calendarList.textContent = error?.error?.message
      || "???????????????";
    calendarList.classList.remove("muted");
    renderDebug(error);
  } finally {
    calendarSave.disabled = false;
  }
});

calendarList.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-calendar-delete]");
  if (!button) return;
  const eventDate = button.dataset.calendarDelete;
  const response = await fetch(
    `/api/v1/users/${consoleUserId}/calendar-overrides/${eventDate}`,
    { method: "DELETE" },
  );
  if (response.ok || response.status === 404) {
    const items = readLocalSnapshot(calendarSnapshotKey, [])
      .filter((item) => item.date !== eventDate);
    writeLocalSnapshot(calendarSnapshotKey, items);
    renderCalendarOverrides(items);
    await loadAgenda(agendaDate.value || shanghaiDateString());
  }
});

async function checkHealth() {
  try {
    const response = await fetch("/api/v1/health");
    const data = await response.json();
    health.textContent = data.status === "ok" ? "????" : "????";
    health.classList.toggle("ok", data.status === "ok");
    if (data.server_time) {
      serverClockBaseMs = new Date(data.server_time).getTime();
      serverClockFetchedAtMs = Date.now();
      renderClock();
    }
  } catch {
    health.textContent = "?????";
    clock.textContent = "????????";
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
    campusState.textContent = "????";
    campusSummary.textContent = "???????????";
    renderDebug(error);
  });
  const accessGranted = await initializeAccess();
  if (!accessGranted) return;
  await loadDemos({ autoRun: true }).catch(() => {
    demoButtons.textContent = "??????";
  });
  agendaDate.value = shanghaiDateString();
  scheduleCursorDate = agendaDate.value;
  weeklyStart.value = nextWeeklyMonday();
  serviceWorkerRegistration().catch(() => {});
  loadReminderSettings().catch((error) => {
    reminderState.textContent = "???????????";
    renderDebug(error);
  });
  loadAgenda(agendaDate.value).catch((error) => {
    agendaState.textContent = "????";
    agendaList.textContent = "???????????????????";
    renderDebug(error);
  });
  loadWeeklyDemos().catch((error) => {
    weeklyDemoButtons.textContent = "???????????";
    renderDebug(error);
  });
  loadMemories().catch((error) => renderDebug(error));
  loadTimetable().catch((error) => renderDebug(error));
  loadCalendarOverrides().catch((error) => renderDebug(error));
}

initializeApp();
