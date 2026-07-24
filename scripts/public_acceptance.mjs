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
          tasks.some((item) => item.title.includes("高等数学")),
          "高等数学课程名称不能丢失",
        ),
        expectTrue(
          tasks.some((item) => item.title.includes("大学英语")),
          "大学英语课程名称不能丢失",
        ),
        expectText(data.answer, "取快递", "回复应提到取快递"),
      ];
    },
  },
  {
    id: "non_contiguous_course_periods",
    now: "2026-07-24T07:00:00+08:00",
    query: "今天第1、3节有课，第四节以后去图书馆自习1小时。",
    check(data) {
      const courses = taskItems(data).filter(
        (item) => item.title.includes("课程"),
      );
      return [
        expectAtLeast(courses.length, 2, "不连续节次必须保留为两个固定块"),
        expectTrue(
          courses.some((item) => item.start_at.slice(11, 16) === "08:05"),
          "第1节开始时间应为08:05",
        ),
        expectTrue(
          courses.some((item) => item.start_at.slice(11, 16) === "10:00"),
          "第3节开始时间应为10:00",
        ),
      ];
    },
  },
  {
    id: "next_week_date",
    query: "下周一去图书馆自习1小时。",
    check(data) {
      return [
        expectEqual(
          data.time_context?.target_date,
          "2026-07-27",
          "下周一必须换算为正确日期",
        ),
      ];
    },
  },
  {
    id: "month_day_date",
    query: "7月31日去图书馆自习1小时。",
    check(data) {
      return [
        expectEqual(
          data.time_context?.target_date,
          "2026-07-31",
          "月日表达必须换算为正确日期",
        ),
      ];
    },
  },
  {
    id: "past_date_clarification",
    query: "本周三去图书馆自习1小时。",
    check(data) {
      return [
        expectEqual(
          data.status,
          "needs_clarification",
          "明确的过去日期不能静默生成计划",
        ),
        expectText(data.answer, "已经过去", "应说明日期已过去并请用户确认"),
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
  {
    id: "live_weather_and_unknown_poi",
    query:
      "今天下午4点从第七教学楼出发，去图书馆学习90分钟，之后到东操场跑步30分钟，请结合今天的天气安排，校内骑电瓶车。",
    check(data) {
      const tasks = taskItems(data);
      const firstTravel = (data.plan?.items || []).find(
        (item) => item.item_type === "travel",
      );
      return [
        expectEqual(data.status, "completed", "未知教学楼应能由高德补齐"),
        expectEqual(tasks.length, 2, "学习和跑步都应安排"),
        expectEqual(
          firstTravel?.start_at,
          "2026-07-24T16:00:00+08:00",
          "首段通勤必须从用户给定时间开始",
        ),
        expectEqual(
          data.data_freshness?.route,
          "live_api",
          "路线应来自高德实时接口",
        ),
        expectEqual(
          data.data_freshness?.weather,
          "live_api",
          "天气应来自实时接口",
        ),
      ];
    },
  },
  {
    id: "bicycle_mode",
    query:
      "今天14点从第六教学楼出发，骑自行车去图书馆自习1小时，再去菜鸟驿站取快递，18点前结束。",
    check(data) {
      const travel = (data.plan?.items || []).filter(
        (item) => item.item_type === "travel",
      );
      return [
        expectEqual(data.status, "completed", "自行车场景应可完整规划"),
        expectTrue(travel.length >= 2, "应包含两段自行车通勤"),
        expectTrue(
          travel.every((item) => item.travel_mode === "bicycle"),
          "用户说自行车后不能改用步行或电瓶车",
        ),
      ];
    },
  },
  {
    id: "peak_congestion",
    query:
      "今天15:55从图书馆出发，步行去菜鸟驿站取快递，17点前完成。",
    check(data) {
      const travel = (data.plan?.items || []).find(
        (item) => item.item_type === "travel",
      );
      return [
        expectTruthy(travel, "应生成首段通勤"),
        expectTrue(
          (travel?.congestion_delay_min || 0) > 0,
          "跨越集中通行时段必须增加通勤时间",
        ),
        expectTrue(
          (data.warnings || []).some(
            (warning) => warning.code === "PEAK_CONGESTION",
          ),
          "应主动提醒校园高峰影响",
        ),
      ];
    },
  },
  {
    id: "jd_before_closing",
    query: "今天21点去京东快递取件，帮我安排一下。",
    check(data) {
      const parcel = taskItems(data).find((item) =>
        item.title.includes("京东"),
      );
      return [
        expectEqual(data.status, "completed", "京东22点前应能安排"),
        expectTruthy(parcel, "京东取件任务不能丢失"),
        expectTrue(
          !parcel || parcel.end_at <= "2026-07-24T22:00:00+08:00",
          "京东取件不能超过22:00",
        ),
      ];
    },
  },
  {
    id: "jd_after_closing",
    query: "今天21:45去京东快递取件，帮我看看能不能安排。",
    check(data) {
      return [
        expectEqual(data.status, "partial", "无法在22点前完成时应判为不可行"),
        expectText(data.answer, "22:00", "应解释京东22点关闭"),
      ];
    },
  },
  {
    id: "library_closing_boundary",
    query: "今天22点去图书馆自习30分钟，可以吗？",
    check(data) {
      const study = taskItems(data).find((item) =>
        item.title.includes("自习"),
      );
      return [
        expectEqual(data.status, "completed", "22:00至22:30仍在整体开放时段"),
        expectTruthy(study, "临近闭馆的自习任务不能丢失"),
        expectEqual(
          study?.end_at,
          "2026-07-24T22:30:00+08:00",
          "自习应在22:30闭馆前结束",
        ),
      ];
    },
  },
  {
    id: "track_closing_boundary",
    query: "今天20:45去东操场跑步30分钟，可以吗？",
    check(data) {
      return [
        expectEqual(data.status, "completed", "操场全天开放，普通跑步可以超过21点"),
        expectTrue(
          /21:00|不计入阳光长跑|计入时段/.test(data.answer),
          "回复应区分场地开放与阳光长跑计入时段",
        ),
      ];
    },
  },
  {
    id: "explicit_rain_boundary",
    query:
      "今天15点后先去东操场跑步30分钟，再去图书馆学习1小时，17点以后有雨，18点前结束。",
    check(data) {
      const run = taskItems(data).find((item) => item.title.includes("跑步"));
      return [
        expectEqual(data.status, "completed", "用户提供的降雨边界应参与规划"),
        expectTruthy(run, "跑步任务不能丢失"),
        expectTrue(
          !run || run.end_at <= "2026-07-24T17:00:00+08:00",
          "户外任务应在用户给定降雨时间前完成",
        ),
        expectText(data.answer, "17:00", "回复应复述用户提供的天气边界"),
      ];
    },
  },
  {
    id: "clinic_weekend_hours",
    query: "周末下午校医院几点可以就诊？",
    check(data) {
      return [
        expectText(data.answer, "13:30", "周末下午门诊应从13:30开始"),
        expectText(data.answer, "16:00", "周末下午门诊应在16:00结束"),
      ];
    },
  },
  {
    id: "northwest_sun_run",
    query: "西北田径场阳光长跑什么时候可以计入？",
    check(data) {
      return [
        expectText(data.answer, "18:30", "西北田径场应从18:30计入"),
        expectText(data.answer, "21:00", "西北田径场应到21:00结束"),
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

const requestedCase = process.env.YICHENG_CASE;
const selectedCases = requestedCase
  ? cases.filter((item) => item.id === requestedCase)
  : cases;
if (!selectedCases.length) {
  throw new Error(`Unknown YICHENG_CASE: ${requestedCase}`);
}

const results = [];
for (let index = 0; index < selectedCases.length; index += 1) {
  const result = await runCase(selectedCases[index], index);
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
