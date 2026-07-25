# API 契约

基础路径：`/api/v1`

所有时间均使用带时区的 ISO 8601 字符串，业务时区默认为
`Asia/Shanghai`。所有错误响应都包含 `request_id`、`trace_id` 和稳定的
错误码。

## 健康检查

`GET /api/v1/health`

返回数据库、知识库、模型、路线和天气能力的当前状态。外部服务未配置
不等于应用故障；离线核心可用时，服务仍可正常提供 Demo。

## Demo 列表

`GET /api/v1/demos`

返回三个固定 Demo 的 `id`、标题、说明和输入语句。

## 运行 Demo

`POST /api/v1/demos/{demo_id}/run`

可用 ID：

- `demo_01_normal`
- `demo_02_emergency`
- `demo_03_degraded`

Demo 强制采用离线模式，保证比赛演示不依赖外部网络。

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
  "mode": "offline",
  "client_context": {
    "current_location_id": null,
    "now": "2026-07-23T12:00:00+08:00"
  }
}
```

`mode`：

- `offline`：只用当前学校已加载或浏览器已缓存的数据，最稳定；
- `auto`：已配置实时服务时优先调用，否则降级；
- `live`：请求实时增强，但提供者失败时仍执行降级逻辑。

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

## 个人数据备份与恢复

- `GET /api/v1/users/{user_id}/profile?thread_id={thread_id}`：导出个人
  课表、长期记忆、校历调整、提醒设置和该会话的当前计划；
- `POST /api/v1/users/{user_id}/profile/restore`：把 `1.0` 版本的数据包
  恢复到指定用户。

导出的服务端数据不含测试密码、登录令牌、模型密钥或地图密钥。网页端会
额外把只保存在当前浏览器中的习惯历史和个性化开关写入
`client_state`；该字段只由网页恢复，后端会忽略。

恢复规则：

- 长期记忆按 `key` 合并或更新；
- 校历调整按日期合并或更新；
- 备份中包含课表时，使用该课表覆盖当前课表；
- 提醒设置整体更新；
- 当前计划生成新的计划和日程项 ID，避免与原设备记录冲突；
- 恢复前不会删除原有记忆或校历记录，失败时也不会清空浏览器旧数据。

数据包最多包含 100 条记忆、500 个课程时段和 366 条校历调整。当前公开
测试版仍以 Vercel 临时运行环境为主，因此这个接口和网页导出功能用于
跨设备迁移与主动备份；正式长期运营仍应接入持久化数据库。

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
- `POST /api/v1/weeks/{plan_id}/events`：记录完成、部分完成或延期；
- `POST /api/v1/weeks/{plan_id}/replan`：按事件最小扰动重排；
- `GET /api/v1/weeks/{plan_id}/versions`：查看历史版本。

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
