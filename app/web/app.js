const $ = (selector) => document.querySelector(selector);
const queryInput = $("#query");
const submitButton = $("#submit");
const resetButton = $("#reset");
const modeSelect = $("#mode");
const timeline = $("#timeline");
const planTitle = $("#plan-title");
const taskStatuses = $("#task-statuses");
const answer = $("#answer");
const assistantActions = $("#assistant-actions");
const warnings = $("#warnings");
const freshness = $("#freshness");
const health = $("#health");
const saveState = $("#save-state");
const demoButtons = $("#demo-buttons");
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
const timetableName = $("#timetable-name");
const termStart = $("#term-start");
const termEnd = $("#term-end");
const timetableFile = $("#timetable-file");
const timetableImport = $("#timetable-import");
const timetableSummary = $("#timetable-summary");
const timetableClear = $("#timetable-clear");
const adjustmentPanel = $(".adjustment-panel");
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
const memorySnapshotKey = "yicheng_memory_snapshot";
const timetableSnapshotKey = "yicheng_timetable_snapshot";
const planSnapshotKey = "yicheng_current_plan_snapshot";

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

function clientContextSnapshot() {
  const memories = readLocalSnapshot(memorySnapshotKey, []);
  const timetableData = readLocalSnapshot(timetableSnapshotKey, null);
  const previousPlan = readLocalSnapshot(planSnapshotKey, null);
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
    previous_plan: previousPlan,
  };
}

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
  avoid_rain: {
    label: "避雨偏好",
    placeholder: "是或否",
    category: "preference",
  },
  avoid_tight_schedule: {
    label: "避免行程太紧",
    placeholder: "是或否",
    category: "preference",
  },
  preferred_locations: {
    label: "常用地点",
    placeholder: "例如：图书馆、东操场",
    category: "preference",
  },
  custom_note: {
    label: "其他习惯",
    placeholder: "例如：晚上更适合运动",
    category: "habit",
  },
};

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
  const items = data.plan?.items || [];
  const locationNames = data.location_names || {};
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
      const location = item.location_id
        ? locationNames[item.location_id] || "地点待确认"
        : "";
      const duration = Math.max(
        0,
        Math.round((new Date(item.end_at) - new Date(item.start_at)) / 60000),
      );
      const reason = isTravel
        ? item.congestion_delay_min > 0
          ? `${item.source === "live_api" ? "高德返回" : "校园路线基准"} ${item.base_duration_min} 分钟，高峰额外预留 ${item.congestion_delay_min} 分钟`
          : `已按所选出行方式预留 ${duration} 分钟`
        : item.reason === "固定或用户锁定任务"
          ? "这是你明确给出的固定安排"
          : "已结合优先级、通勤和可用时间安排";
      return `
        <div class="timeline-item ${isTravel ? "travel" : ""}">
          <div class="time">${timePart(item.start_at)}—${timePart(item.end_at)}</div>
          <div class="rail"><span></span></div>
          <div class="content">
            <strong>${escapeHtml(title)}</strong>
            ${location ? `<small>${escapeHtml(location)}</small>` : ""}
            <p>${escapeHtml(reason)}</p>
          </div>
        </div>`;
    }).join("")
    : "没有生成结构化日程。";
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
    (item) => !hiddenTechnicalCodes.has(item.code),
  );
  warnings.classList.toggle("muted", warningItems.length === 0);
  warnings.innerHTML = warningItems.length
    ? warningItems.map((item) => `
      <div class="warning ${item.severity === "error" ? "error" : ""}">
        <strong>${item.severity === "error" ? "需处理" : "数据说明"}</strong>
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
  assistantActions.innerHTML = actions.map((action, index) => `
    <button class="suggestion-button" data-action-index="${index}">
      <strong>${escapeHtml(action.label)}</strong>
      <span>${escapeHtml(action.description)}</span>
    </button>
  `).join("");
  assistantActions.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = lastSuggestedActions[
        Number(button.dataset.actionIndex)
      ];
      if (!action) return;
      queryInput.value = action.query;
      await submitQuery(action.query);
    });
  });
}

function renderResponse(data) {
  if (data.current_plan_saved && data.plan?.status === "valid") {
    writeLocalSnapshot(planSnapshotKey, data.plan);
  }
  answer.textContent = data.answer;
  answer.classList.remove("muted");
  saveState.textContent = data.current_plan_saved
    ? "当前计划已保存"
    : data.plan ? "结果未写入当前计划" : "尚未生成当前计划";
  saveState.classList.toggle("saved", data.current_plan_saved);
  renderTimeline(data);
  renderTaskStatuses(data.task_statuses, data.location_names);
  renderExecution(data.execution_steps);
  renderConstraints(data.constraint_checks);
  renderDiff(data);
  renderEvidence(data);
  renderInsights(data.insights || []);
  renderSuggestedActions(data.suggested_actions);
  renderDebug(data);
}

function renderError(error) {
  const body = error?.error || {};
  answer.textContent = body.message || "请求失败，请稍后重试。";
  answer.classList.remove("muted");
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
  submitButton.textContent = active ? "正在认真规划…" : "交给易程智策";
}

async function runRequest(url, options = {}) {
  setLoading(true);
  try {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw data;
    renderResponse(data);
    return data;
  } catch (error) {
    renderError(error);
    throw error;
  } finally {
    setLoading(false);
  }
}

async function submitQuery(rawQuery) {
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
  await runRequest("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: consoleUserId,
      thread_id: consoleThreadId,
      query,
      mode: modeSelect.value,
      client_context: clientContextSnapshot(),
    }),
  }).catch(() => {});
}

submitButton.addEventListener("click", async () => {
  await submitQuery(queryInput.value);
});

resetButton.addEventListener("click", async () => {
  setLoading(true);
  try {
    const response = await fetch("/api/v1/demos/reset", { method: "POST" });
    const data = await response.json();
    if (!response.ok) throw data;
    queryInput.value = "";
    timeline.className = "timeline empty";
    timeline.textContent = "演示已复位，请从案例一开始。";
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
  demoButtons.innerHTML = demos.map((demo) => `
    <button data-demo="${escapeHtml(demo.id)}">${escapeHtml(demo.title)}</button>
  `).join("");
  demoButtons.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      const demo = demos.find((item) => item.id === button.dataset.demo);
      queryInput.value = demo.query;
      modeSelect.value = "offline";
      demoButtons.querySelectorAll("button")
        .forEach((item) => item.classList.toggle("active", item === button));
      await runRequest(`/api/v1/demos/${demo.id}/run`, {
        method: "POST",
      }).catch(() => {});
    });
  });
}

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
  if (["avoid_rain", "avoid_tight_schedule", "avoid_congestion"].includes(key)) {
    if (["是", "需要", "开启", "true"].includes(value.toLowerCase())) return true;
    if (["否", "不需要", "关闭", "false"].includes(value.toLowerCase())) return false;
    throw new Error("这一项请填写“是”或“否”。");
  }
  if (key === "preferred_locations") {
    return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
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
  if (["avoid_rain", "avoid_tight_schedule", "avoid_congestion"].includes(key)) {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) return value.join("、");
  return String(value);
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

async function fileToImportPayload(file) {
  const extension = file.name.split(".").pop().toLowerCase();
  if (extension === "xlsx") {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return { format: "xlsx_base64", content: btoa(binary) };
  }
  if (extension === "csv" || extension === "json") {
    return { format: extension, content: await file.text() };
  }
  throw new Error("请选择 .xlsx、.csv 或 .json 课表文件。");
}

function renderTimetable(data) {
  const entries = data.entries || [];
  timetableSummary.classList.toggle("muted", entries.length === 0);
  timetableClear.hidden = entries.length === 0;
  if (!entries.length) {
    timetableSummary.textContent = "当前还没有导入个人课表。";
    return;
  }
  const grouped = new Map();
  entries.forEach((entry) => {
    if (!grouped.has(entry.weekday)) grouped.set(entry.weekday, []);
    grouped.get(entry.weekday).push(entry);
  });
  timetableSummary.innerHTML = `
    <div class="timetable-status">
      <strong>${escapeHtml(data.timetable?.name || "我的课表")}</strong>
      <span>${entries.length}门次课程 · 已启用</span>
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
            }节${entry.location ? ` · ${escapeHtml(entry.location)}` : ""}</span>
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
  if (data.entries?.length) {
    writeLocalSnapshot(timetableSnapshotKey, data);
    renderTimetable(data);
    return;
  }
  renderTimetable(readLocalSnapshot(timetableSnapshotKey, data));
}

timetableImport.addEventListener("click", async () => {
  const file = timetableFile.files?.[0];
  if (!file) {
    timetableSummary.textContent = "请先选择一份课表文件。";
    timetableSummary.classList.remove("muted");
    return;
  }
  timetableImport.disabled = true;
  timetableImport.textContent = "正在识别课表…";
  try {
    const filePayload = await fileToImportPayload(file);
    const response = await fetch(
      `/api/v1/users/${consoleUserId}/timetable/import`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: timetableName.value.trim() || "我的课表",
          term_start: termStart.value || null,
          term_end: termEnd.value || null,
          ...filePayload,
        }),
      },
    );
    const data = await response.json();
    if (!response.ok) throw data;
    writeLocalSnapshot(timetableSnapshotKey, data);
    renderTimetable(data);
    timetableFile.value = "";
    answer.textContent = `课表已经导入，共识别 ${data.imported_count} 门次课程。之后你只要告诉我想做什么，我会自动避开上课时间。`;
    answer.classList.remove("muted");
  } catch (error) {
    timetableSummary.textContent = error instanceof Error
      ? error.message
      : error?.error?.message || "课表暂时没有导入成功。";
    timetableSummary.classList.remove("muted");
    renderDebug(error);
  } finally {
    timetableImport.disabled = false;
    timetableImport.textContent = "导入并启用课表";
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
  }
});

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

checkHealth();
setInterval(renderClock, 30000);
updateMemoryPlaceholder();
loadMemories().catch((error) => renderDebug(error));
loadTimetable().catch((error) => renderDebug(error));
loadDemos().catch(() => {
  demoButtons.textContent = "案例加载失败";
});
