const baseUrl = (process.env.YICHENG_BASE_URL || "http://127.0.0.1:8000")
  .replace(/\/$/, "");

const cases = [
  {
    id: "course_constraints",
    now: "2026-07-24T07:00:00+08:00",
    query:
      "今天第1至2节有高等数学课，第3至4节有大学英语课。下课后去图书馆自习90分钟，18点前取快递。",
    check(data) {
      const tasks = taskItems(data);
      return [
        expectEqual(data.status, "completed", "应生成完整计划"),
        expectAtLeast(tasks.length, 3, "课程和生活任务应全部保留"),
        expectTrue(
          tasks.some((item) => item.title.includes("课程")),
          "明确节次必须形成固定课程约束",
        ),
        expectText(data.answer, "取快递", "回复应提到取快递"),
      ];
    },
  },
  {
    id: "fixed_event_order",
    query:
      "今天15:00到16:30固定参加社团会议，之后从学生活动中心去取快递，18点前完成，再去图书馆自习1小时。",
    check(data) {
      const tasks = taskItems(data);
      const meeting = tasks.find((item) => item.title.includes("社团会议"));
      const parcel = tasks.find((item) => item.title.includes("取快递"));
      return [
        expectTruthy(meeting, "固定会议不能丢失"),
        expectEqual(
          meeting?.start_at?.slice(11, 16),
          "15:00",
          "固定会议开始时间不能改变",
        ),
        expectTruthy(parcel, "取快递不能丢失"),
        expectTrue(
          !parcel || parcel.end_at <= "2026-07-24T18:00:00+08:00",
          "取快递必须在明确截止时间前完成",
        ),
      ];
    },
  },
  {
    id: "sf_closing_constraint",
    query: "今天19点去顺丰快递取件，帮我看看能不能安排。",
    check(data) {
      const parcel = taskItems(data).find((item) =>
        item.title.includes("快递"),
      );
      return [
        expectTrue(
          data.status !== "completed" || !parcel || parcel.end_at <=
            "2026-07-24T18:00:00+08:00",
          "顺丰18:00关闭，不能生成19:00可执行计划",
        ),
        expectText(data.answer, "18", "回复应解释顺丰关闭时间"),
      ];
    },
  },
  {
    id: "library_floor_hours",
    query: "图书馆七楼晚上几点关闭？",
    check(data) {
      return [
        expectEqual(data.status, "completed", "知识问答应正常完成"),
        expectText(data.answer, "21:30", "七楼开放时间应回答21:30"),
      ];
    },
  },
  {
    id: "dormitory_curfew",
    query: "周四晚上宿舍楼几点关门？",
    check(data) {
      return [
        expectText(data.answer, "23:00", "周四宿舍门禁应回答23:00"),
      ];
    },
  },
  {
    id: "hot_water_hours",
    query: "晚上宿舍什么时候有热水？",
    check(data) {
      return [
        expectText(data.answer, "16:30", "晚间热水应从16:30开始"),
        expectText(data.answer, "24:00", "晚间热水应持续到24:00"),
      ];
    },
  },
  {
    id: "handbook_grounding",
    query: "学生考试作弊会受到什么处分？请按学生手册回答。",
    check(data) {
      return [
        expectEqual(data.status, "completed", "学生手册问答应正常完成"),
        expectTrue(
          data.answer.length >= 80,
          "制度回答应包含足够的依据和解释",
        ),
        expectTrue(
          !/当前知识库中没有检索到/.test(data.answer),
          "学生手册内容应能被检索到",
        ),
      ];
    },
  },
  {
    id: "caring_infeasible",
    query:
      "今天17:30从第六教学楼出发，要去图书馆学习2小时、取快递、跑步30分钟，必须18点前全部结束。",
    check(data) {
      return [
        expectEqual(data.status, "partial", "时间不足时应明确给出部分方案"),
        expectTrue(
          /来不及|时间不够|无法|差|调整/.test(data.answer),
          "回复应自然解释为什么排不下",
        ),
        expectTrue(!data.answer.startsWith("你好"), "回复不应机械问候"),
      ];
    },
  },
];

function taskItems(data) {
  return (data.plan?.items || []).filter((item) => item.item_type === "task");
}

function pass(message) {
  return { passed: true, message };
}

function fail(message, actual) {
  return { passed: false, message, actual };
}

function expectEqual(actual, expected, message) {
  return actual === expected ? pass(message) : fail(message, actual);
}

function expectTrue(condition, message) {
  return condition ? pass(message) : fail(message, false);
}

function expectTruthy(value, message) {
  return value ? pass(message) : fail(message, value);
}

function expectAtLeast(actual, minimum, message) {
  return actual >= minimum ? pass(message) : fail(message, actual);
}

function expectText(actual, expected, message) {
  return String(actual || "").includes(expected)
    ? pass(message)
    : fail(message, String(actual || "").slice(0, 240));
}

async function runCase(testCase, index) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 65_000);
  try {
    const response = await fetch(`${baseUrl}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        user_id: `acceptance_${testCase.id}`,
        thread_id: `acceptance_${testCase.id}_${Date.now()}_${index}`,
        query: testCase.query,
        mode: "live",
        client_context: {
          now: testCase.now || "2026-07-24T13:00:00+08:00",
        },
      }),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      return {
        id: testCase.id,
        passed: false,
        failures: [`HTTP ${response.status}: ${JSON.stringify(data)}`],
      };
    }
    const assertions = [
      ...testCase.check(data),
      expectTrue(
        !/(?:location_id|live_api|structured|task_id|preferred_period)/.test(
          data.answer,
        ),
        "面向用户的回复不应暴露内部变量",
      ),
    ];
    return {
      id: testCase.id,
      passed: assertions.every((item) => item.passed),
      status: data.status,
      taskCount: taskItems(data).length,
      answerPreview: String(data.answer || "").slice(0, 180),
      failures: assertions
        .filter((item) => !item.passed)
        .map((item) =>
          item.actual === undefined
            ? item.message
            : `${item.message}（实际：${JSON.stringify(item.actual)}）`,
        ),
    };
  } catch (error) {
    return {
      id: testCase.id,
      passed: false,
      failures: [error instanceof Error ? error.message : String(error)],
    };
  } finally {
    clearTimeout(timer);
  }
}

const results = [];
for (let index = 0; index < cases.length; index += 1) {
  const result = await runCase(cases[index], index);
  results.push(result);
  console.log(
    `${result.passed ? "PASS" : "FAIL"} ${result.id}` +
      (result.failures?.length ? ` — ${result.failures.join("；")}` : ""),
  );
}

const passed = results.filter((item) => item.passed).length;
console.log(`\n${passed}/${results.length} scenarios passed against ${baseUrl}`);
if (passed !== results.length) {
  process.exitCode = 1;
}
