# API 契约

基础路径：`/api/v1`

所有时间均使用带时区的 ISO 8601 字符串，业务时区默认为
`Asia/Shanghai`。所有错误响应都包含 `request_id`、`trace_id` 和稳定的
错误码。

## 健康检查

`GET /api/v1/health`

返回数据库、知识库、模型、路线和天气能力的当前状态。外部服务未配置
不等于应用故障；确定性规划核心仍会给出可核验结果或明确的缺失信息。

## Demo 列表

`GET /api/v1/demos`

返回三个固定 Demo 的 `id`、标题、说明和输入语句。

## 运行 Demo

`POST /api/v1/demos/{demo_id}/run`

可用 ID：

- `demo_01_normal`
- `demo_02_emergency`
- `demo_03_degraded`

Demo 使用冻结输入与可审计数据快照保证结果可复现；正式交互默认保持联网，
按配置调用在线模型、高德路线和天气，不把“离线模式”作为产品卖点。

## 复位 Demo

`POST /api/v1/demos/reset`

只清除 `demo_user` 的会话、运行和计划状态，不修改知识库或静态数据。
复位后可从案例一重新演示，也可以直接运行案例二或案例三。

## 规划对话

`POST /api/v1/chat`

请求示例：

```json
{
  "user_id": "demo_user",
  "thread_id": "optional_thread",
  "query": "明天下午自习两个小时，18点前取快递，晚上跑步",
  "old_plan_id": null,
  "mode": "auto",
  "client_context": {
    "current_location_id": null,
    "now": "2026-07-23T12:00:00+08:00"
  }
}
```

`mode`：

- `auto`：推荐值；已配置实时服务时优先调用，提供者失败时明确降级；
- `live`：请求实时增强，但提供者失败时仍执行降级逻辑。
- `offline`：仅保留为开发回归兼容选项，不用于当前比赛产品口径。

响应核心字段：

```json
{
  "request_id": "req_...",
  "trace_id": "trace_...",
  "thread_id": "thread_...",
  "status": "completed",
  "answer": "已生成可执行日程……",
  "plan": {
    "id": "plan_...",
    "status": "valid",
    "items": [],
    "metrics": {}
  },
  "clarifications": [],
  "warnings": [],
  "data_freshness": {
    "route": "demo_fixture",
    "weather": "demo_fixture",
    "knowledge": "rag"
  },
  "location_names": {
    "library": "图书馆"
  },
  "previous_plan": null,
  "plan_diff": [],
  "adjustment_reason": null,
  "constraint_checks": [],
  "execution_steps": [],
  "insights": [],
  "current_plan_saved": true
}
```

调整类输入若未显式提供 `old_plan_id`，系统会按 `thread_id` 读取最近一份
有效计划作为 `previous_plan`。`plan_diff` 只比较任务项，不把自动生成的
通勤项当作用户任务变化。只有通过全部硬约束的计划才会保存为当前计划。

`client_context.campus` 可携带前端已选择的校园及地点目录。后端按
`campus_id` 注册并隔离这些地点；没有导入该校规则包时，不会借用默认
学校的开放时间、节次或制度。

`status`：

- `completed`：生成了可行计划；
- `needs_clarification`：关键条件不足，需要用户补充；
- `partial`：仅保留了可安排部分，响应中会包含错误级问题。

## 校园地点发现

- `GET /api/v1/campuses/current`：读取项目默认校园；
- `POST /api/v1/campuses/discover`：输入学校/校区与城市，从高德按教学、
  学习、餐饮、住宿、运动和生活服务六类建立首批校园地点目录。

请求示例：

```json
{
  "school_name": "浙江大学紫金港校区",
  "city": "杭州",
  "radius_m": 1800
}
```

返回的 `campus` 应由前端保存在浏览器中，并在后续
`client_context.campus` 中带回。分类发现允许部分成功：某一类暂时超时
不会使整个校园建立失败；用户实际提及未收录地点时仍会继续实时搜索。

## 读取计划

`GET /api/v1/plans/{plan_id}`

不存在时返回 `PLAN_NOT_FOUND`。

## 长期记忆管理

- `GET /api/v1/users/{user_id}/memories`：读取用户保存的偏好与习惯；
- `POST /api/v1/users/{user_id}/memories`：新增或按 `key` 更新记忆；
- `PATCH /api/v1/users/{user_id}/memories/{memory_id}`：修改内容或启停；
- `DELETE /api/v1/users/{user_id}/memories/{memory_id}`：删除记忆。

记忆只保存用户主动设置的内容。规划时仅将启用的记忆作为软偏好，本轮
输入、课程节次、开放时间、截止时间等硬约束始终优先。

## 长期日程、提醒与系统日历

- `GET /api/v1/users/{user_id}/agenda`：读取服务端当前实例中的日程；
- `POST /api/v1/users/{user_id}/agenda/contextual`：先用请求中的个人
  快照同步当前执行实例，再返回日程；
- `GET /api/v1/users/{user_id}/reminders/due`：读取当前到点提醒；
- `POST /api/v1/users/{user_id}/reminders/due/contextual`：携带个人
  快照检查到点提醒；
- `GET /api/v1/users/{user_id}/agenda.ics`：导出当前实例中的日历；
- `POST /api/v1/users/{user_id}/agenda.ics/contextual`：携带个人快照
  生成包含闹钟的日历文件。

三个 `contextual` 接口接收当前会话的已校验上下文，用于在同一次请求内
完成计划、提醒和日历计算。杭电助手同步的课程及校园安排直接保存在服务端，
不通过客户端上下文传递，并始终作为不可随意移动的事实约束。

## 自然语言周规划

`POST /api/v1/weeks/plan/from-text`

请求示例：

```json
{
  "user_id": "test_user",
  "campus_id": "hdu_xiasha",
  "week_start": "2026-07-27",
  "query": "周五22:00前完成课程设计，共8小时，其中编码4小时、测试2小时、报告2小时；本周跑步2次，每次40分钟，尽量晚上去东操场。",
  "timezone": "Asia/Shanghai",
  "use_personal_context": true
}
```

接口先将自然语言转换为结构化目标，再扣除已导入课表、校历覆盖和启用的
长期偏好，最后生成跨日时间块。明确的“尽量晚上”等偏好只影响候选时段
排序，不会错误软化用户的截止时间；用户没有提供必要时长时返回
`WEEKLY_CLARIFICATION_REQUIRED`，不会擅自缩短或猜测复杂任务。

结构化入口和滚动重排：

- `POST /api/v1/weeks/plan`：提交完整结构化周目标；
- `GET /api/v1/weeks/{week_start}?user_id=...`：读取当前周计划；
- `POST /api/v1/weeks/{plan_id}/days/{date}/materialize`：把某日周分配
  结合课表、校历、路线、场馆和天气落成经校验的日计划；
- `POST /api/v1/weeks/{plan_id}/events`：记录完成、部分完成或延期；
- `POST /api/v1/weeks/{plan_id}/replan`：按事件最小扰动重排；

每日落地会在一个数据库事务内完成 Plan、PlanItems 与周分配绑定；并发请求
返回同一胜出计划。若排程期间分配状态、已完成分钟或时间窗发生变化，返回
可重试的 `WEEKLY_GROUNDING_SNAPSHOT_CHANGED`（409），不保存过期快照。
分配响应中的 `completed_duration_min` 是该块累计完成分钟，重排只计算
`allocated_duration_min - completed_duration_min`。
- `GET /api/v1/weeks/{week_start}/versions?user_id=...&campus_id=...`：
  查看指定用户、校区与周起始日的历史版本。

滚动重排请求示例：

```json
{
  "trigger_type": "new_task",
  "capacities": [
    {
      "date": "2026-07-27",
      "windows": [
        {
          "start_at": "2026-07-27T18:00:00+08:00",
          "end_at": "2026-07-27T21:00:00+08:00"
        }
      ]
    }
  ],
  "invalidated_allocation_ids": [],
  "additional_goals": [
    {
      "title": "新增答辩提纲",
      "deadline": "2026-07-27T21:00:00+08:00",
      "total_duration_min": 60,
      "min_chunk_min": 60,
      "max_chunk_min": 60,
      "splittable": false
    }
  ]
}
```

若不提供 `capacities` 或 `availability`，接口会按当前个人课表、校历和已启用
偏好重新计算本周容量。新版本不会覆盖旧版本；`lineage_id` 用于跨版本识别
同一目标、阶段或分配，`source_allocation_id` 指向直接来源时间块。对已经被
新版本替代的旧计划再次重排、写入完成事件或执行每日落地都会返回
`WEEKLY_PLAN_SUPERSEDED`，避免旧版本污染最新状态和并发分叉。
若重排计算期间同一基线的完成进度发生变化，保存 V2 时返回可重试的
`WEEKLY_REPLAN_SNAPSHOT_CHANGED`（409）；调用方应读取最新周计划后重试，
不能原样重复提交旧快照。

## 错误格式

```json
{
  "request_id": "req_...",
  "trace_id": "trace_...",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "请求参数不合法",
    "details": [
      {
        "field": "body.query",
        "reason": "String should have at least 1 character"
      }
    ],
    "retryable": false
  }
}
```

前端只依赖稳定错误码，不应解析 Python 异常文本。
