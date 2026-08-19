const baseUrl = (
  process.env.YICHENG_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");
const stamp = Date.now();

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function requestHeaders() {
  const headers = { "content-type": "application/json" };
  const response = await fetch(`${baseUrl}/api/v1/auth/status`);
  const status = await response.json();
  if (!status.enabled) return headers;

  const username = process.env.YICHENG_USERNAME;
  const password = process.env.YICHENG_PASSWORD;
  if (!username || !password) {
    throw new Error(
      "公网已启用测试登录，请设置 YICHENG_USERNAME 和 YICHENG_PASSWORD",
    );
  }
  const login = await fetch(`${baseUrl}/api/v1/auth/login`, {
    method: "POST",
    headers,
    body: JSON.stringify({ username, password }),
  });
  const data = await login.json();
  if (!login.ok) {
    throw new Error(`测试账号登录失败：HTTP ${login.status}`);
  }
  return { ...headers, authorization: `Bearer ${data.access_token}` };
}

const acceptanceHeaders = await requestHeaders();

async function api(
  path,
  {
    method = "GET",
    body,
    expectedStatus = 200,
    responseType = "json",
    timeoutMs = 65_000,
  } = {},
) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: acceptanceHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = responseType === "text"
      ? await response.text()
      : await response.json();
    if (response.status !== expectedStatus) {
      throw new Error(
        `${method} ${path} 返回 HTTP ${response.status}：`
        + (typeof data === "string" ? data.slice(0, 300) : JSON.stringify(data)),
      );
    }
    return { data, headers: response.headers };
  } finally {
    clearTimeout(timer);
  }
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

function taskItems(payload) {
  return (payload.plan?.items || []).filter(
    (item) => item.item_type === "task",
  );
}

const results = [];

results.push(await runCase("public_entry_and_health", async () => {
  const health = await api("/api/v1/health");
  assert(health.data.status === "ok", "健康检查未返回 ok");
  assert(health.data.service, "健康检查缺少服务名称");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`${baseUrl}/`, { signal: controller.signal });
    const html = await response.text();
    assert(response.ok, `公网首页返回 HTTP ${response.status}`);
    assert(html.includes("易程智策"), "公网首页缺少作品名称");
    assert(html.includes("我的长期日程"), "公网首页缺少长期日程模块");
    assert(html.includes("一周目标如何真正落到每天"), "公网首页缺少周规划模块");
    assert(html.includes("杭电助手"), "公网首页缺少杭电助手账号与数据入口");
    assert(!html.includes("把课表和习惯带到新设备"), "公网首页仍残留旧备份入口");
  } finally {
    clearTimeout(timer);
  }
}));

results.push(await runCase("three_competition_demos", async () => {
  await api("/api/v1/demos/reset", { method: "POST" });
  try {
    const normal = (
      await api("/api/v1/demos/demo_01_normal/run", { method: "POST" })
    ).data;
    const normalTasks = taskItems(normal);
    assert(normal.status === "completed", "案例一未完成");
    assert(normal.current_plan_saved === true, "案例一没有保存当前计划");
    assert(normalTasks.length === 3, "案例一任务数量不是 3");
    assert(
      new Set(normalTasks.map((item) => item.task_id)).size === 3,
      "案例一存在重复或丢失任务",
    );
    assert(
      !normal.answer.includes("天气有变化时"),
      "案例一错误使用天气调整开场",
    );
    assert(
      normal.answer.includes("不需要卡着分钟一路赶"),
      "案例一缺少自然、贴心的执行说明",
    );

    const changed = (
      await api("/api/v1/demos/demo_02_emergency/run", { method: "POST" })
    ).data;
    assert(changed.status === "completed", "案例二未完成");
    assert(taskItems(changed).length === 3, "案例二修改后丢失任务");
    assert(changed.plan_diff?.length >= 3, "案例二没有完整调整对比");
    assert(
      changed.answer.includes("只调整受影响的部分"),
      "案例二没有说明最小扰动原则",
    );

    const weather = (
      await api("/api/v1/demos/demo_03_degraded/run", { method: "POST" })
    ).data;
    const run = taskItems(weather).find((item) => item.task_id === "run");
    assert(weather.status === "completed", "案例三未完成");
    assert(run, "案例三漏掉跑步任务");
    assert(
      run.end_at <= "2026-07-24T17:00:00+08:00",
      "案例三跑步没有移到降雨边界之前",
    );
    assert(
      weather.answer.includes("天气有变化时，安全比赶进度更重要"),
      "案例三缺少天气关怀开场",
    );
    assert(weather.answer.includes("带把伞"), "案例三缺少带伞提醒");
    assert(
      !(weather.warnings || []).some((item) => item.code === "WEATHER_RISK"),
      "案例三调整后仍存在天气风险",
    );
  } finally {
    await api("/api/v1/demos/reset", { method: "POST" });
  }
}));

results.push(await runCase("weekly_planning_demos", async () => {
  const catalog = (await api("/api/v1/weeks/demos/catalog")).data;
  assert(catalog.length === 3, "周规划案例数量不是 3");
  const output = {};
  for (const item of catalog) {
    const query = new URLSearchParams({
      user_id: `product_weekly_${stamp}`,
    });
    output[item.id] = (
      await api(
        `/api/v1/weeks/demos/${item.id}/run?${query}`,
        { method: "POST" },
      )
    ).data;
  }

  const sprint = output.weekly_demo_01_sprint.weekly_plan;
  assert(sprint.status === "valid", "多目标周计划不是可行状态");
  assert(
    sprint.metrics.allocated_duration_min === 740,
    "多目标周计划分配时长错误",
  );
  const overload = output.weekly_demo_02_overload.weekly_plan;
  assert(overload.status === "infeasible", "容量冲突案例未识别不可行");
  assert(
    overload.metrics.unallocated_duration_min === 240,
    "容量冲突缺口不是 240 分钟",
  );
  const portable = output.weekly_demo_03_portable;
  assert(portable.weekly_plan.status === "valid", "个性化周计划不可行");
  assert(
    portable.capacity_summary.timetable_applied === true,
    "个性化周计划没有应用个人课表",
  );
  assert(
    portable.capacity_summary.memory_labels.length === 2,
    "个性化周计划没有应用两项偏好",
  );
}));

results.push(await runCase("weekly_completion_idempotency", async () => {
  const query = new URLSearchParams({
    user_id: `product_event_${stamp}`,
  });
  const response = (
    await api(
      `/api/v1/weeks/demos/weekly_demo_01_sprint/run?${query}`,
      { method: "POST" },
    )
  ).data;
  const plan = response.weekly_plan;
  const allocation = plan.allocations[0];
  assert(allocation, "周计划没有可执行时间块");
  const event = {
    event_type: "partial",
    allocation_id: allocation.id,
    occurred_at: allocation.earliest_start,
    completed_duration_min: Math.min(
      30,
      allocation.allocated_duration_min,
    ),
    client_event_id: `product-event-${stamp}`,
  };
  const eventQuery = new URLSearchParams({ user_id: plan.user_id });
  const path = `/api/v1/weeks/${plan.id}/events?${eventQuery}`;
  const first = (await api(path, { method: "POST", body: event })).data;
  const duplicate = (await api(path, { method: "POST", body: event })).data;
  assert(first.applied === true, "首次周任务完成记录没有生效");
  assert(duplicate.applied === false, "重复周任务事件被二次扣减");
}));

results.push(await runCase("memory_crud", async () => {
  const user = `product_memory_${stamp}`;
  const created = (
    await api(`/api/v1/users/${user}/memories`, {
      method: "POST",
      expectedStatus: 201,
      body: {
        category: "preference",
        key: "buffer_min",
        label: "日程缓冲时间",
        value: 15,
        enabled: true,
      },
    })
  ).data;
  assert(created.value === 15, "长期记忆创建值错误");
  const updated = (
    await api(`/api/v1/users/${user}/memories/${created.id}`, {
      method: "PATCH",
      body: { value: 20, enabled: false },
    })
  ).data;
  assert(updated.value === 20 && updated.enabled === false, "长期记忆修改失败");
  const listed = (await api(`/api/v1/users/${user}/memories`)).data;
  assert(listed.items.length === 1, "长期记忆列表数量错误");
  await api(`/api/v1/users/${user}/memories/${created.id}`, {
    method: "DELETE",
    expectedStatus: 204,
    responseType: "text",
  });
  const cleared = (await api(`/api/v1/users/${user}/memories`)).data;
  assert(cleared.items.length === 0, "长期记忆删除后仍然存在");
}));

results.push(await runCase("agenda_reminders_and_calendar_export", async () => {
  const user = `product_agenda_${stamp}`;
  const csv = [
    "课程名称,星期,开始节次,结束节次,地点,周次",
    "高等数学,星期五,1,2,第六教学楼,1-16",
    "大学英语,星期五,3,4,第七教学楼,1-16",
  ].join("\n");
  const imported = (
    await api(`/api/v1/users/${user}/timetable/import`, {
      method: "POST",
      expectedStatus: 201,
      body: {
        name: "产品验收课表",
        format: "csv",
        content: csv,
        term_start: "2026-07-20",
        term_end: "2026-11-30",
      },
    })
  ).data;
  assert(imported.imported_count === 2, "课表没有导入两门课程");

  for (const [key, label, value] of [
    ["usual_bedtime", "常用就寝时间", "23:00"],
    ["usual_wake_time", "常用起床时间", "06:30"],
    ["sleep_goal_hours", "希望睡眠时长", 7.5],
  ]) {
    await api(`/api/v1/users/${user}/memories`, {
      method: "POST",
      expectedStatus: 201,
      body: {
        category: "habit",
        key,
        label,
        value,
        enabled: true,
      },
    });
  }

  const settings = (
    await api(`/api/v1/users/${user}/reminders/settings`, {
      method: "PUT",
      body: {
        enabled: true,
        browser_notifications: false,
        bedtime_enabled: true,
        course_lead_min: 30,
        early_course_wakeup_min: 90,
        meeting_lead_min: 20,
        study_lead_min: 15,
        exercise_lead_min: 15,
        task_lead_min: 10,
        bedtime_lead_min: 30,
        quiet_start: "23:00:00",
        quiet_end: "06:30:00",
      },
    })
  ).data;
  assert(settings.settings.course_lead_min === 30, "上课提醒设置未保存");
  assert(settings.settings.bedtime_enabled === true, "就寝关怀未启用");

  const range = new URLSearchParams({
    start_date: "2026-07-23",
    end_date: "2026-07-24",
  });
  const agenda = (
    await api(`/api/v1/users/${user}/agenda?${range}`)
  ).data;
  assert(agenda.summary.course_count === 2, "长期日程漏掉个人课程");
  assert(
    agenda.reminders.some(
      (item) =>
        item.kind === "bedtime"
        && item.notify_at === "2026-07-23T22:30:00+08:00",
    ),
    "长期日程没有生成就寝提醒",
  );
  assert(
    agenda.reminders.some((item) => item.kind === "wakeup"),
    "早八课程没有生成起床提醒",
  );

  const dueQuery = new URLSearchParams({
    now: "2026-07-23T22:30:00+08:00",
    window_min: "1",
  });
  const due = (
    await api(`/api/v1/users/${user}/reminders/due?${dueQuery}`)
  ).data;
  assert(
    due.reminders.some((item) => item.kind === "bedtime"),
    "到点查询没有返回就寝提醒",
  );

  const exported = await api(
    `/api/v1/users/${user}/agenda.ics?${range}`,
    { responseType: "text" },
  );
  assert(
    exported.headers.get("content-type")?.includes("text/calendar"),
    "日历导出类型错误",
  );
  assert(exported.data.includes("SUMMARY:高等数学"), "日历漏掉课程");
  assert(exported.data.includes("SUMMARY:准备休息"), "日历漏掉就寝事件");
  assert(exported.data.includes("TRIGGER:-PT90M"), "日历漏掉早八起床闹钟");
  assert(exported.data.includes("TRIGGER:-PT30M"), "日历漏掉提前提醒");
}));

results.push(await runCase("heavy_study_care", async () => {
  const user = `product_care_${stamp}`;
  const chat = (
    await api("/api/v1/chat", {
      method: "POST",
      body: {
        user_id: user,
        thread_id: `product_care_thread_${stamp}`,
        query: "2026年7月25日8点开始在图书馆自习7小时。",
        mode: "offline",
        client_context: { now: "2026-07-24T20:00:00+08:00" },
      },
    })
  ).data;
  assert(chat.status === "completed", "高强度学习计划未生成");
  const range = new URLSearchParams({
    start_date: "2026-07-25",
    end_date: "2026-07-25",
  });
  const agenda = (
    await api(`/api/v1/users/${user}/agenda?${range}`)
  ).data;
  assert(
    agenda.care_suggestions.some(
      (item) => item.id === "balance_heavy_study",
    ),
    "高强度学习日没有生活平衡建议",
  );
  assert(
    agenda.care_suggestions.some(
      (item) => item.id.startsWith("meal_gap_"),
    ),
    "高强度学习日没有用餐提醒",
  );
}));

const passed = results.filter(Boolean).length;
console.log(`\n${passed}/${results.length} product journeys passed against ${baseUrl}`);
if (passed !== results.length) process.exit(1);
