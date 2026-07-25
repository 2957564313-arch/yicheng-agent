# 易程智策：分层周规划与滚动重排方案

> 状态：核心链路已实现并进入持续验收
> 定位：这是现有“单日可执行规划”的上层能力，不替换现有日规划器。  
> 对外表达：面向大学生复杂学习生活目标的周计划生成、每日落地与动态调整。  
> 实现说明：LangGraph、FastAPI 等只作为实现方式，不作为作品宣传主线。

## 1. 为什么不是简单的“排七天”

单日任务较少时，用户自己确实可以完成粗略安排。系统真正有价值的场景应同时满足：

- 任务跨越多天，并有不同截止时间；
- 一项任务需要拆成多个阶段或多个专注时段；
- 每天存在课表、会议、实验、社团等固定约束；
- 场馆开放时间、通勤、天气和节假日会改变可用时间；
- 用户希望兼顾学习、生活、锻炼和休息，而不是只追求“塞满”；
- 临时调课、拖堂、下雨、任务延期后，原计划需要局部修复；
- 未完成任务需要滚入后续日期，但不能把整周推倒重来。

因此新版能力定义为：

> **分层周规划 + 每日可执行排程 + 事件驱动的最小扰动滚动重排**

## 2. 核心创新点

### 2.1 目标—阶段—时间块的三级拆解

用户输入的是目标，例如“周五前完成课程设计”，系统将其转换为：

1. 周目标：完成课程设计；
2. 阶段：资料整理、方案设计、编码、测试、撰写报告；
3. 时间块：周一 90 分钟、周三 120 分钟、周四 90 分钟。

系统不能把总时长直接切成完全相同的小块。需要同时考虑：

- 阶段先后依赖；
- 最小连续时长；
- 截止时间前的安全余量；
- 用户高效时段；
- 当天课程密度与精力负担；
- 同地点任务合并带来的通勤节省。

### 2.2 周层负责“分配”，日层负责“落地”

周层只决定“哪一天承担多少任务”，不直接猜每一分钟。

日层复用现有规划能力，继续严格校验：

- 固定课程与用户固定安排；
- 最早开始、最晚结束和截止时间；
- 场馆开放时段；
- 地点与真实通勤；
- 校园拥堵加时；
- 天气与户外风险；
- 节假日、补课、停课和临时校历覆盖；
- 用户明确锁定的任务和顺序。

这样能够避免周规划为了全局好看，生成当天无法执行的安排。

### 2.3 每日滚动而非整周重算

每天结束或发生突发事件时，系统读取完成情况：

- 已完成：冻结，不再改变；
- 进行中：保留已投入时长，只安排剩余部分；
- 未完成：根据截止风险滚入后续可行时段；
- 新增任务：插入剩余周计划；
- 用户锁定：除非用户明确解除，否则禁止移动。

重排目标优先级：

1. 不违反硬约束；
2. 不错过截止时间；
3. 尽量保留原计划；
4. 尽量减少跨地点通勤；
5. 尽量平衡每日负担；
6. 尽量符合用户偏好。

### 2.4 可解释的风险前置

系统不仅给出结果，还应明确提示：

- 哪个任务存在延期风险；
- 风险来自总时长不足、可用窗口太少，还是前置任务未完成；
- 哪几天负担过重；
- 哪些任务已预留安全余量；
- 天气、开放时间或补课安排会影响哪一天；
- 如果无法全部完成，应该调整截止时间、任务时长还是优先级。

### 2.5 杭电知识约束与个人数据分层

当前参赛版本固定服务杭州电子科技大学下沙校区，优先把本校场景做深。

公共校园知识层提供：

- 13 节课的准确起止时间；
- 学期、教学周、法定节假日与临时补课；
- 图书馆、体育场馆、快递点、宿舍和校医院开放规则；
- 阳光长跑计入时段、热水供应和校园拥堵窗口；
- 学生手册与校园制度知识检索；
- 高德本校地点、步行/骑行通勤与杭州天气。

个人数据层由每位用户自行维护：

- 个人课表与固定活动；
- 学习、运动、用餐和出行偏好；
- 缓冲时间、常用地点与个性化建议开关；
- 周目标、完成进度和历史调整反馈。

规划时，学校公共规则不能被个人偏好覆盖；个人课表和用户明确锁定的安排
同样属于硬约束。个性化习惯只用于推荐，不得未经确认自动写入日程。

## 3. 首个高价值演示场景

### 用户输入

> 请帮我安排未来七天。周五 22:00 前完成课程设计，预计还要 8 小时，其中编码必须在测试之前；周三前读完论文并做 2 小时汇报准备；这周跑步两次，每次 40 分钟。我的课表已经导入，周二晚上有社团会议，周四下午实验可能延长一小时。尽量不要连续两天熬夜。

### 系统应完成

1. 读取个人课表和固定活动；
2. 将课程设计拆分为编码、测试、报告三个阶段；
3. 按依赖关系和截止时间分配到多天；
4. 把论文阅读与汇报准备放在周三之前；
5. 将两次跑步分散安排，并结合天气；
6. 每天调用日规划器加入通勤、开放时间和缓冲；
7. 对周四实验延长建立风险预案；
8. 输出周概览、每天安排、DDL 风险和调整理由。

### 突发变化

> 周二的编码没做完，周四实验确定延长一小时，但周五晚上不想改。

### 系统应重排

- 冻结已完成任务；
- 保留周五晚间锁定安排；
- 将周二剩余编码拆分到周三、周四可行窗口；
- 测试阶段仍必须晚于编码；
- 只修改受影响的任务块；
- 给出新旧计划差异和原计划保留率。

## 4. 领域数据模型

### 4.1 WeeklyGoal

```text
id                       唯一标识
user_id                  用户标识
campus_id                当前学校/校区
title                    目标名称
description              用户补充说明
week_start               周一日期
earliest_start           最早可开始时间
deadline                 最终截止时间
total_duration_min       预计总投入时长
remaining_duration_min   剩余时长
splittable               是否可跨时段拆分
min_chunk_min            单个时间块最小时长
max_chunk_min            单个时间块最大时长
max_chunks_per_day       每天最多安排多少块
importance               1—5
hard_deadline            是否为不可突破的硬截止
preferred_periods        偏好时段
avoided_periods          尽量避免的时段
preferred_locations      偏好地点
energy_level             low / medium / high
status                   pending / active / completed / cancelled
source                   user / imported / inferred
created_at
updated_at
```

约束：

- `remaining_duration_min <= total_duration_min`；
- 不可拆分任务只能生成一个时间块；
- 可拆分任务的时间块不得低于 `min_chunk_min`；
- `hard_deadline=true` 时，不允许用“以后补做”掩盖不可行；
- 未经用户确认，系统不能擅自缩短 `total_duration_min`。

### 4.2 GoalStage

```text
id
goal_id
title
sequence
duration_min
remaining_duration_min
depends_on_stage_ids
splittable
min_chunk_min
preferred_location
completion_criteria
status
```

阶段用于表达“先编码、后测试”这类顺序约束。没有明确阶段的普通目标可以只有一个默认阶段。

### 4.3 WeeklyPlan

```text
id
user_id
campus_id
week_start
week_end
timezone
version
status                   draft / valid / at_risk / infeasible / archived
created_at
updated_at
baseline_plan_id         重排前版本
trigger_type             initial / daily_rollover / event / manual
```

### 4.4 DayAllocation

```text
id
weekly_plan_id
date
goal_id
stage_id
allocated_duration_min
earliest_start
latest_end
preferred_period
location_id
priority_score
risk_score
locked
daily_plan_id
status                   proposed / scheduled / completed / deferred
```

周层生成 `DayAllocation`，再转换成现有日规划器可以识别的 `Task`。

### 4.5 CompletionEvent

```text
id
user_id
weekly_plan_id
allocation_id
event_type               completed / partial / skipped / delayed / new_task
occurred_at
completed_duration_min
remaining_duration_min
reason
client_event_id          客户端幂等键
created_at
```

## 5. 状态结构

周规划使用独立状态，不把现有日规划状态无限膨胀：

```python
class WeeklyPlanningState(TypedDict, total=False):
    request_id: str
    trace_id: str
    user_id: str
    campus_id: str
    timezone: str
    now_iso: str
    week_start: str
    week_end: str

    query: str
    goals: list[dict]
    stages: list[dict]
    preferences: dict

    timetable_constraints: list[dict]
    calendar_constraints: list[dict]
    venue_constraints: list[dict]
    weather_summary: list[dict]
    memory_context: list[dict]

    daily_capacity: list[dict]
    allocations: list[dict]
    daily_plans: list[dict]
    weekly_issues: list[dict]
    risk_summary: list[dict]

    previous_weekly_plan: dict | None
    plan_diff: list[dict]
    replan_count: int
    max_replans: int

    final_answer: str
    final_weekly_plan: dict | None
    status: str
    node_trace: list[dict]
```

## 6. 五个核心节点

### 6.1 UnderstandWeek：理解目标

职责：

- 识别目标、总时长、DDL、优先级、是否可拆分；
- 识别明确的阶段与依赖；
- 区分硬约束与软偏好；
- 未给总时长且无法合理默认时，只追问一个最关键问题；
- 读取课表、记忆和学校校历，但不能让记忆覆盖本轮要求。

伪代码：

```text
parse query with structured LLM output
merge explicit client goals
normalize all datetimes to active timezone
for each goal:
    validate deadline and duration
    create default stage if no stages
    preserve explicit dependencies
if critical information missing:
    return clarification
return goals + stages + preferences
```

### 6.2 BuildCapacity：构建每日可用容量

职责：

- 展开七天课表、固定日程和校历覆盖；
- 计算每天可用于灵活任务的时间窗；
- 标注高精力时段、拥堵时段、天气和场馆限制；
- 不把动态天气当成整周绝对事实，超出可靠预报范围只做风险提示。

伪代码：

```text
for day in week:
    hard_blocks = timetable + fixed_events + calendar_overrides
    free_windows = subtract(day_bounds, hard_blocks)
    attach venue windows
    attach reliable weather window or forecast uncertainty
    calculate usable_minutes by energy band
return daily_capacity
```

### 6.3 AllocateWeek：跨日分配

职责：

- 在不违反阶段依赖的前提下，从截止时间向前安排；
- DDL 风险高的任务优先；
- 保证每个任务至少有一个截止前安全余量；
- 限制单日负担，避免把任务堆到最后一天；
- 尽量把同地点任务聚合；
- 输出 `DayAllocation`，不直接输出最终时间轴。

初版优先使用确定性启发式算法。只有在启发式方案无法满足约束或质量不足时，再引入 CP-SAT。

伪代码：

```text
order stages by:
    hard deadline risk
    dependency depth
    remaining duration
    importance

for stage in ordered stages:
    candidate_days = days before deadline and after dependencies
    score each day by:
        available capacity
        deadline safety
        workload balance
        preferred period
        location affinity
        energy match
    split remaining duration into valid chunks
    allocate chunks to best-scoring days
    if remaining duration > 0:
        emit infeasible issue with exact shortage
return allocations
```

### 6.4 GroundDays：生成并校验每日计划

职责：

- 将每个分配块转换为现有 `Task`；
- 调用现有日规划器；
- 加入路线、拥堵、天气、开放时间和缓冲；
- 若某一天不可行，返回可修复容量，而不是静默丢任务；
- 每日最多尝试两次，不允许无限循环。

伪代码：

```text
for day in week:
    tasks = fixed constraints + allocations[day]
    daily_result = run existing daily planner
    if infeasible:
        return failed allocations and available alternatives
return daily_plans
```

### 6.5 RepairAndRespond：滚动修复与解释

职责：

- 根据日规划失败、完成事件或新增任务做局部重排；
- 冻结已完成、已开始和用户锁定内容；
- 只回收受影响的分配块；
- 计算计划差异、保留率和延期风险；
- 生成自然、关怀且可执行的回复。

伪代码：

```text
freeze completed + started + locked allocations
collect affected goals and returned capacity
reallocate only affected remaining duration
re-run daily grounding for changed days
validate weekly hard constraints
calculate preservation rate and risk metrics
compose weekly overview + today focus + warnings + choices
```

## 7. 规划目标函数

硬约束必须全部满足：

- 固定课程与固定活动不能移动；
- 阶段依赖不能逆序；
- 硬截止时间不能突破；
- 场馆关闭时不能安排对应任务；
- 日计划不能时间重叠；
- 跨地点任务必须留出通勤；
- 用户锁定任务不能被系统移动；
- 已完成任务不能被重写。

软目标按以下顺序优化：

```text
minimize:
    1000 × hard_violation_count
  + 300 × missed_deadline_count
  + 120 × overdue_risk
  + 80  × moved_locked_neighbor_count
  + 40  × workload_imbalance
  + 20  × total_travel_minutes
  + 15  × fragmented_chunk_count
  + 10  × preference_penalty
```

具体权重在测试后调整，但硬约束的代价必须显著高于任何软目标。

## 8. API 设计

### 8.1 生成周计划

`POST /api/v1/weeks/plan`

普通用户优先使用自然语言入口：

`POST /api/v1/weeks/plan/from-text`

该入口支持从一段中文中识别多个周目标、总时长、阶段时长和依赖、重复次数、
截止时间、偏好时段与地点。规则解析足够明确时直接进入确定性分配；仍有关键
字段缺失时返回一组可操作的追问；配置模型后可在规则解析无法完整覆盖时补充
结构化理解，模型不可用时自动回退，不影响已明确输入。

请求：

```json
{
  "user_id": "test_user",
  "week_start": "2026-07-27",
  "query": "周五前完成课程设计……",
  "goals": [],
  "client_context": {
    "campus": {},
    "timetable": {},
    "calendar_overrides": [],
    "memories": [],
    "personalization": {}
  }
}
```

响应重点字段：

```json
{
  "status": "completed",
  "answer": "自然语言周计划说明",
  "weekly_plan": {},
  "daily_summaries": [],
  "deadline_risks": [],
  "plan_diff": [],
  "suggested_actions": []
}
```

### 8.2 查询周计划

`GET /api/v1/weeks/{week_start}?user_id=...`

### 8.3 记录执行事件

`POST /api/v1/weeks/{plan_id}/events`

必须使用 `client_event_id` 保证重复点击不会重复扣减剩余时长。

### 8.4 滚动重排

`POST /api/v1/weeks/{plan_id}/replan`

触发原因：

- `daily_rollover`
- `task_incomplete`
- `new_task`
- `fixed_event_changed`
- `weather_changed`
- `manual`

### 8.5 手动锁定与解锁

`PATCH /api/v1/weeks/{plan_id}/allocations/{allocation_id}`

允许用户：

- 锁定时间块；
- 修改预计时长；
- 标记完成或部分完成；
- 取消任务；
- 调整优先级；
- 关闭某个习惯建议。

## 9. SQLite 表

新增表：

```sql
weekly_goals
goal_stages
weekly_plans
day_allocations
completion_events
weekly_plan_versions
```

关键索引：

```text
weekly_goals(user_id, week_start, status)
goal_stages(goal_id, sequence)
weekly_plans(user_id, week_start, version)
day_allocations(weekly_plan_id, date, status)
completion_events(weekly_plan_id, occurred_at)
UNIQUE completion_events(user_id, client_event_id)
```

保留周计划历史版本，不能覆盖旧版本，以便展示“调整前后对比”和计算原计划保留率。

## 10. 前端交互

首版不做复杂甘特图，使用四个对用户真正有用的区域：

1. **本周目标**：总进度、剩余时长、DDL 风险；
2. **七日概览**：每天任务块、固定课程和负担等级；
3. **今天怎么做**：复用现有详细时间轴；
4. **变化说明**：哪些任务移动了、为什么移动、保留率多少。

用户操作：

- 完成；
- 部分完成；
- 今天没做；
- 锁定；
- 延后；
- 新增任务；
- 重新规划受影响部分。

调试信息默认折叠。前台不得展示内部英文变量、内部节点名、数据库 ID 或模型原始 JSON。

## 11. 个性化与记忆边界

记忆可以建议，不能擅自写入硬计划：

- 连续多周在相近时间自习，可询问是否加入本周；
- 用户拒绝一次后进入冷却；
- 连续拒绝两次后停止主动建议；
- 用户可以总开关关闭个性化建议；
- 学习习惯不得覆盖课表、DDL、场馆开放时间和本轮明确要求；
- 不同学校、不同校区的地点习惯必须隔离。

## 12. 测试矩阵

### 12.1 单元测试

- 不可拆分目标只生成一个块；
- 分块不低于最小时长；
- 阶段依赖顺序正确；
- 任务不跨越硬截止；
- 每日最大块数生效；
- 已完成任务冻结；
- 锁定任务不移动；
- 重复完成事件幂等；
- 计划版本不会覆盖；
- 未经核验的地点或开放信息不得替代杭电知识库中的已核验规则。

### 12.2 集成测试

- 导入课表后生成一周计划；
- 多目标、多 DDL、多阶段同时存在；
- 场馆关闭导致跨日迁移；
- 某天大雨导致户外任务调整；
- 临时加课触发局部重排；
- 未完成任务滚入后续日期；
- 新增高优先级任务后保留原计划；
- 法定节假日有个人活动但无常规课程；
- 调休工作日没有学校通知时不臆造补课；
- 当前版本固定使用杭电下沙校区知识底座。

### 12.3 三个演示 fixture

1. `weekly_01_multi_deadline.json`  
   多个截止时间、课程设计阶段拆分、跑步分散安排。

2. `weekly_02_rollover.json`  
   周二任务未完成，滚动到周三、周四，保留周五锁定安排。

3. `weekly_03_weather_and_class_change.json`  
   天气变化与临时加课同时发生，只重排受影响部分。

## 13. 验收指标

| 指标 | 首版目标 |
|---|---:|
| 硬约束违反率 | 0% |
| 硬截止满足率 | ≥ 95%（客观可行样本） |
| 阶段依赖正确率 | 100% |
| 日计划可执行率 | ≥ 95% |
| 任务覆盖率 | ≥ 95% |
| 滚动重排成功率 | ≥ 90% |
| 原计划保留率 | ≥ 75% |
| 未完成事件幂等率 | 100% |
| 跨学校规则串用率 | 0% |

若输入在客观上不可行，系统的正确行为不是伪造完整计划，而是：

- 返回 `at_risk` 或 `infeasible`；
- 精确说明缺少多少分钟、哪项约束造成问题；
- 给出两个以内真正可执行的调整方案。

## 14. 分阶段开发

### 阶段 A：模型与存储

- 新增周目标、阶段、分配块和完成事件 schema；
- 新增 SQLite 表与 repository；
- 增加幂等与版本测试。

### 阶段 B：确定性周分配器

- 计算每日容量；
- 支持 DDL、分块、阶段依赖和负担平衡；
- 转换为现有日规划任务；
- 完成首个 fixture。

### 阶段 C：每日落地与滚动修复

- 调用现有日规划器；
- 接收完成/未完成事件；
- 最小扰动重排；
- 计算差异、风险和保留率。

### 阶段 D：前端周视图

- 本周目标；
- 七日概览；
- 今天时间轴；
- 完成、部分完成、锁定和延后操作；
- 变化说明。

### 阶段 E：跨学校与验收

- 使用第二所学校 Campus Profile 测试；
- 完成三个演示 fixture；
- 扩充周规划测试集；
- 记录实测指标并用于参赛 PPT。

## 15. 冻结规则

首版暂不实现：

- 多个大模型智能体相互辩论；
- 强化学习；
- 自动读取教务系统账号；
- 后台无限期自主运行；
- 复杂团队协作排程；
- 自动修改用户课表；
- 无依据预测学校补课；
- 七天以外的长期项目管理。

首版必须守住：

- 周规划只是上层分配，日规划仍做硬校验；
- 任何任务不得静默丢失；
- 不可行必须明确说明；
- 记忆只做建议；
- 用户可以手动管理与锁定；
- 学校规则必须来自当前学校知识包；
- 动态地点来自当前学校高德范围；
- 每次自动重排都能解释变化。

## 16. 参赛表达

推荐的一句话：

> 易程智策不仅回答“今天怎么排”，还能够把跨日目标拆成可执行阶段，结合课表、校园规则、通勤和天气形成一周计划，并在临时变化发生后以最小扰动方式滚动调整。

推荐的三个创新点：

1. **跨日目标分解与校园时空约束联合规划**；
2. **周分配—日校验的分层决策闭环**；
3. **基于完成状态的最小扰动滚动重排**。

这三个创新点同时具备：

- 可演示性：能清楚展示初始计划、突发变化和调整前后差异；
- 可量化性：可以统计 DDL 满足率、可执行率和保留率；
- 可实现性：复用现有日规划、课表、知识库、地图和天气能力；
- 个性化：学校公共规则统一，每位用户通过课表、记忆和完成反馈形成自己的计划。
