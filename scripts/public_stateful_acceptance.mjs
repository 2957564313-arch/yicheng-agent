const baseUrl = (process.env.YICHENG_BASE_URL || "http://127.0.0.1:8000")
  .replace(/\/$/, "");
const stamp = Date.now();

async function requestHeaders() {
  const headers = { "content-type": "application/json" };
  const status = await fetch(`${baseUrl}/api/v1/auth/status`).then(
    (response) => response.json(),
  );
  if (!status.enabled) return headers;
  const username = process.env.YICHENG_USERNAME;
  const password = process.env.YICHENG_PASSWORD;
  if (!username || !password) {
    throw new Error(
      "公网已启用测试登录，请设置 YICHENG_USERNAME 和 YICHENG_PASSWORD",
    );
  }
  const response = await fetch(`${baseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers,
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`测试账号登录失败：HTTP ${response.status}`);
  return { ...headers, authorization: `Bearer ${data.access_token}` };
}

const acceptanceHeaders = await requestHeaders();

async function chat(payload) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 65_000);
  try {
    const response = await fetch(`${baseUrl}/api/v1/chat`, {
      method: "POST",
      headers: acceptanceHeaders,
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${JSON.stringify(data)}`);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function taskItems(data) {
  return (data.plan?.items || []).filter((item) => item.item_type === "task");
}

function travelItems(data) {
  return (data.plan?.items || []).filter((item) => item.item_type === "travel");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function runCase(id, runner) {
  try {
    await runner();
    console.log(`PASS ${id}`);
    return true;
  } catch (error) {
    console.error(`FAIL ${id} — ${error.message}`);
    return false;
  }
}

const results = [];

results.push(await runCase("browser_plan_snapshot_cold_start", async () => {
  const first = await chat({
    user_id: `stateful_seed_${stamp}`,
    thread_id: `stateful_seed_thread_${stamp}`,
    query: "今天14点后去图书馆自习1小时，再去取快递，18点前结束。",
    mode: "offline",
    client_context: { now: "2026-07-24T13:00:00+08:00" },
  });
  assert(first.status === "completed", "基线计划未完成");
  const coldUser = `stateful_cold_${stamp}`;
  const coldThread = `stateful_cold_thread_${stamp}`;
  const browserPlan = {
    ...first.plan,
    id: `client_plan_${stamp}`,
    user_id: coldUser,
    thread_id: coldThread,
  };
  const second = await chat({
    user_id: coldUser,
    thread_id: coldThread,
    query: "把图书馆自习延长30分钟，其他任务保持不变，还是18点前结束。",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:05:00+08:00",
      previous_plan: browserPlan,
    },
  });
  assert(second.previous_plan?.id === browserPlan.id, "浏览器计划快照未被接续");
  assert(second.plan?.version === browserPlan.version + 1, "计划版本未递增");
  assert(second.plan_diff?.length > 0, "没有返回新旧计划差异");
}));

results.push(await runCase("memory_snapshot_applied", async () => {
  const data = await chat({
    user_id: `stateful_memory_${stamp}`,
    thread_id: `stateful_memory_thread_${stamp}`,
    query: "今天14点后去图书馆自习1小时，再去菜鸟驿站取快递，18点前结束。",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:00:00+08:00",
      memories: [{
        category: "preference",
        key: "buffer_min",
        label: "日程缓冲时间",
        value: 20,
        enabled: true,
      }],
    },
  });
  const items = data.plan?.items || [];
  const parcel = items.find((item) => item.task_id === "parcel");
  const precedingTravel = [...items]
    .reverse()
    .find((item) => item.item_type === "travel" && item.end_at <= parcel.start_at);
  assert(parcel && precedingTravel, "没有生成快递及其通勤");
  const gap = (new Date(parcel.start_at) - new Date(precedingTravel.end_at)) / 60000;
  assert(gap >= 20, `长期偏好缓冲仅 ${gap} 分钟`);
  assert(
    data.insights?.some(
      (item) =>
        item.title.includes("个性化")
        && item.content.includes("日程缓冲时间"),
    ),
    "界面证据未说明已应用长期偏好",
  );
}));

const timetable = {
  name: "验收课表",
  term_start: "2026-07-20",
  term_end: "2026-08-31",
  enabled: true,
  entries: [{
    course_name: "数据结构",
    weekday: 5,
    start_period: 6,
    end_period: 7,
    location: "第六教学楼",
    weeks: [1],
  }],
};

results.push(await runCase("timetable_snapshot_query", async () => {
  const data = await chat({
    user_id: `stateful_timetable_query_${stamp}`,
    thread_id: `stateful_timetable_query_thread_${stamp}`,
    query: "我今天哪几节有课？",
    mode: "offline",
    client_context: {
      now: "2026-07-24T07:00:00+08:00",
      timetable,
    },
  });
  assert(data.answer.includes("数据结构"), "课表问答漏掉课程名");
  assert(data.answer.includes("第6—7节"), "课表问答漏掉节次");
  assert(data.answer.includes("13:30—15:05"), "课表问答漏掉准确时间");
}));

results.push(await runCase("timetable_snapshot_hard_constraint", async () => {
  const data = await chat({
    user_id: `stateful_timetable_plan_${stamp}`,
    thread_id: `stateful_timetable_plan_thread_${stamp}`,
    query: "今天13点以后去图书馆自习1小时，再取快递，18点前结束。",
    mode: "offline",
    client_context: {
      now: "2026-07-24T12:30:00+08:00",
      timetable,
    },
  });
  const course = taskItems(data).find((item) => item.title === "数据结构");
  assert(course, "规划时漏掉个人课表课程");
  assert(course.start_at === "2026-07-24T13:30:00+08:00", "课程开始时间被修改");
  assert(course.end_at === "2026-07-24T15:05:00+08:00", "课程结束时间被修改");
}));

results.push(await runCase("new_query_does_not_reuse_old_plan", async () => {
  const seed = await chat({
    user_id: `stateful_isolation_${stamp}`,
    thread_id: `stateful_isolation_seed_${stamp}`,
    query: "今天14点后去图书馆自习1小时。",
    mode: "offline",
    client_context: { now: "2026-07-24T13:00:00+08:00" },
  });
  const cleanThread = `stateful_isolation_clean_${stamp}`;
  const snapshot = {
    ...seed.plan,
    id: `isolation_plan_${stamp}`,
    thread_id: cleanThread,
  };
  const data = await chat({
    user_id: seed.plan.user_id,
    thread_id: cleanThread,
    query: "图书馆七楼晚上几点关闭？",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:05:00+08:00",
      previous_plan: snapshot,
    },
  });
  assert(data.plan === null, "独立知识问答错误复用了旧计划");
  assert(data.previous_plan === null, "独立问答不应显示计划调整对比");
  assert(data.answer.includes("21:30"), "独立问答答案错误");
}));

results.push(await runCase("explicit_transport_overrides_memory", async () => {
  const data = await chat({
    user_id: `stateful_mode_${stamp}`,
    thread_id: `stateful_mode_thread_${stamp}`,
    query: "今天14点从第六教学楼出发，步行去图书馆自习1小时。",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:00:00+08:00",
      memories: [{
        category: "preference",
        key: "transport_mode",
        label: "常用出行方式",
        value: "electrobike",
        enabled: true,
      }],
    },
  });
  const travel = travelItems(data)[0];
  assert(travel, "没有生成通勤段");
  assert(travel.travel_mode === "walk", "本轮明确步行没有覆盖长期偏好");
}));

results.push(await runCase("walking_pace_memory_changes_duration", async () => {
  async function travelFor(label, memories) {
    const data = await chat({
      user_id: `stateful_walk_${label}_${stamp}`,
      thread_id: `stateful_walk_${label}_thread_${stamp}`,
      query: "今天14点从第六教学楼出发，步行去图书馆自习1小时。",
      mode: "offline",
      client_context: {
        now: "2026-07-24T13:00:00+08:00",
        memories,
      },
    });
    return travelItems(data)[0];
  }
  const normal = await travelFor("normal", []);
  const slow = await travelFor("slow", [{
    category: "preference",
    key: "walking_speed",
    label: "步行节奏",
    value: "slow",
    enabled: true,
  }]);
  assert(normal && slow, "没有生成用于比较的步行通勤");
  assert(
    slow.base_duration_min > normal.base_duration_min,
    "慢速步行偏好没有增加预留时间",
  );
}));

results.push(await runCase("preferred_place_memory_applied", async () => {
  const data = await chat({
    user_id: `stateful_place_${stamp}`,
    thread_id: `stateful_place_thread_${stamp}`,
    query: "今天14点后自习1小时。",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:00:00+08:00",
      memories: [{
        category: "preference",
        key: "preferred_locations",
        label: "常用地点",
        value: ["第六教学楼"],
        enabled: true,
      }],
    },
  });
  const study = taskItems(data).find((item) => item.title.includes("自习"));
  assert(study, "自习任务丢失");
  assert(
    study.location_id === "teaching_building_6",
    "未采用用户保存的常用自习地点",
  );
}));

results.push(await runCase("makeup_calendar_uses_replacement_weekday", async () => {
  const data = await chat({
    user_id: `stateful_makeup_${stamp}`,
    thread_id: `stateful_makeup_thread_${stamp}`,
    query: "2026年10月10日哪几节有课？",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:00:00+08:00",
      timetable: {
        name: "验收补课课表",
        term_start: "2026-09-28",
        term_end: "2027-01-31",
        enabled: true,
        entries: [{
          course_name: "数据结构",
          weekday: 5,
          start_period: 6,
          end_period: 7,
          location: "第六教学楼",
          weeks: [],
        }],
      },
      calendar_overrides: [{
        date: "2026-10-10",
        action: "makeup",
        replacement_weekday: 5,
        label: "学校通知：补星期五课程",
      }],
    },
  });
  assert(data.answer.includes("数据结构"), "补课日没有载入替代星期的课程");
  assert(data.answer.includes("第6—7节"), "补课课程节次错误");
}));

results.push(await runCase("holiday_suppresses_regular_timetable", async () => {
  const data = await chat({
    user_id: `stateful_holiday_${stamp}`,
    thread_id: `stateful_holiday_thread_${stamp}`,
    query: "2026年10月2日要上课吗？",
    mode: "offline",
    client_context: {
      now: "2026-07-24T13:00:00+08:00",
      timetable: {
        name: "验收节假日课表",
        term_start: "2026-09-28",
        term_end: "2027-01-31",
        enabled: true,
        entries: [{
          course_name: "本不应出现的星期五课程",
          weekday: 5,
          start_period: 1,
          end_period: 2,
          location: "第六教学楼",
          weeks: [],
        }],
      },
    },
  });
  assert(data.answer.includes("国庆节"), "未识别法定节假日");
  assert(
    !data.answer.includes("本不应出现的星期五课程"),
    "法定节假日错误加载了常规个人课表",
  );
  assert(
    /不执行常规课程|常规课程不占用/.test(data.answer),
    "没有明确说明常规课表被节假日暂停",
  );
}));

results.push(await runCase("conversation_appends_without_overwriting", async () => {
  const userId = `stateful_append_${stamp}`;
  const threadId = `stateful_append_thread_${stamp}`;
  const first = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "2026年7月28日14点去图书馆自习1小时。",
    mode: "offline",
    client_context: { now: "2026-07-25T10:00:00+08:00" },
  });
  const second = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "另外在2026年7月28日18:30到19:30固定开会，保留已有安排。",
    mode: "offline",
    client_context: {
      now: "2026-07-25T10:05:00+08:00",
      previous_plan: first.plan,
    },
  });
  const titles = taskItems(second).map((item) => item.title);
  assert(titles.includes("图书馆自习"), "追加事项时覆盖了原有自习");
  assert(titles.includes("开会"), "新增会议未加入或标题未清洗");
  assert(
    !/热水开放时间|上课时间第1节/.test(second.answer),
    "回复混入与当前任务无关的知识片段",
  );
}));

results.push(await runCase("conversation_removes_only_requested_task", async () => {
  const userId = `stateful_remove_${stamp}`;
  const threadId = `stateful_remove_thread_${stamp}`;
  const first = await chat({
    user_id: userId,
    thread_id: threadId,
    query: (
      "2026年7月28日14点后去图书馆自习1小时，"
      + "再取快递，然后跑步30分钟，20点前结束。"
    ),
    mode: "offline",
    client_context: { now: "2026-07-25T10:00:00+08:00" },
  });
  const second = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "跑步不去了，其他安排保持不变。",
    mode: "offline",
    client_context: {
      now: "2026-07-25T10:05:00+08:00",
      previous_plan: first.plan,
    },
  });
  const ids = taskItems(second).map((item) => item.task_id);
  assert(ids.includes("study"), "取消跑步时误删了自习");
  assert(ids.includes("parcel"), "取消跑步时误删了取快递");
  assert(!ids.includes("run"), "用户已取消跑步但任务仍被保留");
  assert(
    second.plan_diff?.some(
      (item) => item.task_id === "run" && item.change_type === "removed",
    ),
    "计划差异没有明确记录被取消的跑步",
  );
  assert(second.answer.includes("已经移除"), "回复没有确认取消结果");
}));

results.push(await runCase("conversation_reschedules_only_named_task", async () => {
  const userId = `stateful_move_${stamp}`;
  const threadId = `stateful_move_thread_${stamp}`;
  const first = await chat({
    user_id: userId,
    thread_id: threadId,
    query: (
      "2026年7月30日14点到15点固定自习，"
      + "18:30到19:30固定开会。"
    ),
    mode: "offline",
    client_context: { now: "2026-07-25T10:00:00+08:00" },
  });
  const before = Object.fromEntries(
    taskItems(first).map((item) => [item.task_id, item]),
  );
  const meetingId = Object.keys(before).find(
    (taskId) => before[taskId].title.includes("开会"),
  );
  const studyId = Object.keys(before).find(
    (taskId) => before[taskId].title.includes("自习"),
  );
  const second = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "把开会改到20:00到21:00，自习保持原来的时间。",
    mode: "offline",
    client_context: {
      now: "2026-07-25T10:05:00+08:00",
      previous_plan: first.plan,
    },
  });
  const after = Object.fromEntries(
    taskItems(second).map((item) => [item.task_id, item]),
  );
  assert(
    after[meetingId]?.start_at.endsWith("20:00:00+08:00"),
    "会议没有移动到20:00",
  );
  assert(
    after[meetingId]?.end_at.endsWith("21:00:00+08:00"),
    "会议结束时间错误",
  );
  assert(
    after[studyId]?.start_at === before[studyId]?.start_at,
    "修改会议时误动了自习",
  );
}));

results.push(await runCase("conversation_duration_and_global_shift", async () => {
  const userId = `stateful_duration_${stamp}`;
  const threadId = `stateful_duration_thread_${stamp}`;
  const first = await chat({
    user_id: userId,
    thread_id: threadId,
    query: (
      "2026年7月30日14点到15点固定自习，"
      + "18:30到19:30固定开会。"
    ),
    mode: "offline",
    client_context: { now: "2026-07-25T10:00:00+08:00" },
  });
  const baseline = Object.fromEntries(
    taskItems(first).map((item) => [item.task_id, item]),
  );
  const meetingId = Object.keys(baseline).find(
    (taskId) => baseline[taskId].title.includes("开会"),
  );
  const studyId = Object.keys(baseline).find(
    (taskId) => baseline[taskId].title.includes("自习"),
  );
  const extended = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "把开会延长30分钟，自习保持原时间。",
    mode: "offline",
    client_context: {
      now: "2026-07-25T10:05:00+08:00",
      previous_plan: first.plan,
    },
  });
  const afterDuration = Object.fromEntries(
    taskItems(extended).map((item) => [item.task_id, item]),
  );
  assert(
    afterDuration[meetingId]?.end_at.endsWith("20:00:00+08:00"),
    "会议没有按要求延长30分钟",
  );
  assert(
    afterDuration[studyId]?.start_at === baseline[studyId]?.start_at,
    "延长会议时误动了自习",
  );

  const shifted = await chat({
    user_id: userId,
    thread_id: threadId,
    query: "所有安排顺延30分钟，但开会保持原来的时间。",
    mode: "offline",
    client_context: {
      now: "2026-07-25T10:10:00+08:00",
      previous_plan: extended.plan,
    },
  });
  const afterShift = Object.fromEntries(
    taskItems(shifted).map((item) => [item.task_id, item]),
  );
  assert(
    afterShift[studyId]?.start_at.endsWith("14:30:00+08:00"),
    "全局顺延没有移动可调整的自习",
  );
  assert(
    afterShift[meetingId]?.start_at === afterDuration[meetingId]?.start_at,
    "全局顺延没有尊重“开会保持原时间”",
  );
  assert(
    afterShift[meetingId]?.end_at === afterDuration[meetingId]?.end_at,
    "全局顺延改变了被保护会议的时长",
  );
}));

const passed = results.filter(Boolean).length;
console.log(`\n${passed}/${results.length} stateful scenarios passed against ${baseUrl}`);
if (passed !== results.length) process.exitCode = 1;
