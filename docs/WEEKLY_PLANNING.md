# 易程智策：分层周规划与滚动重排方案

> 状态：可进入开发。该能力位于现有“单日可执行规划”之上，不替换日规划器。LangGraph、FastAPI 只是实现方式，不作为作品宣传主线。

## 一、定位

单日任务较少时，用户自己即可粗略安排。系统真正有价值的场景应同时包含：跨日任务、多个截止时间、阶段依赖、课表和固定活动、场馆开放时间、真实通勤、天气、节假日、临时变化与未完成任务。

新版能力定义为：

> **分层周规划 + 每日可执行排程 + 事件驱动的最小扰动滚动重排**

周层决定“哪一天承担多少任务”，日层继续严格校验课程、固定安排、截止时间、场馆开放、路线、拥堵、天气、校历与用户锁定项。

## 二、三个核心创新点

1. **目标—阶段—时间块三级拆解**  
   把“周五前完成课程设计”拆为资料、编码、测试、报告等阶段，再分配为符合最小连续时长的时间块，并保留阶段依赖。

2. **周分配—日校验的分层闭环**  
   周层做跨日容量分配，日层复用现有规划器加入通勤、开放时间、天气和缓冲。某一天无法落地时，任务返回周层重新分配，不能静默丢失。

3. **基于完成状态的最小扰动滚动重排**  
   已完成、已开始和用户锁定内容冻结；未完成部分滚入后续日期；新增任务仅影响相关时间块。系统展示新旧差异、延期风险和原计划保留率。

## 三、首个高价值演示

用户输入：

> 请帮我安排未来七天。周五 22:00 前完成课程设计，预计还要 8 小时，其中编码必须在测试之前；周三前读完论文并做 2 小时汇报准备；这周跑步两次，每次 40 分钟。我的课表已经导入，周二晚上有社团会议，周四下午实验可能延长一小时。尽量不要连续两天熬夜。

系统应完成：

- 读取个人课表、校历和固定活动；
- 拆分课程设计阶段并维护依赖；
- 按多个 DDL 分配任务；
- 将跑步分散并结合天气；
- 对每天调用日规划器加入通勤、开放时间和缓冲；
- 给周四实验延长建立风险预案；
- 输出周概览、每天安排、DDL 风险和调整理由。

突发变化：

> 周二编码没做完，周四实验确定延长一小时，但周五晚上不想改。

系统应冻结已完成内容和周五锁定项，只回收受影响的编码、测试和实验后任务，重新计算周三、周四可用容量，并展示调整前后差异。

## 四、通用数据模型

### WeeklyGoal

- id、user_id、campus_id、title、description；
- week_start、earliest_start、deadline；
- total_duration_min、remaining_duration_min；
- splittable、min_chunk_min、max_chunk_min、max_chunks_per_day；
- importance、hard_deadline、energy_level；
- preferred_periods、avoided_periods、preferred_locations；
- status、source、created_at、updated_at。

规则：

- 剩余时长不能大于总时长；
- 不可拆分任务只能生成一个时间块；
- 分块不得低于最小时长；
- 硬截止不可用“以后补做”掩盖；
- 未经用户确认不得缩短总任务时长。

### GoalStage

- goal_id、title、sequence、duration_min、remaining_duration_min；
- depends_on_stage_ids、splittable、min_chunk_min；
- preferred_location、completion_criteria、status。

### WeeklyPlan

- user_id、campus_id、week_start、week_end、timezone；
- version、status、baseline_plan_id、trigger_type；
- created_at、updated_at。

### DayAllocation

- weekly_plan_id、date、goal_id、stage_id；
- allocated_duration_min、earliest_start、latest_end；
- preferred_period、location_id、priority_score、risk_score；
- locked、daily_plan_id、status。

### CompletionEvent

- event_type：completed / partial / skipped / delayed / new_task；
- occurred_at、completed_duration_min、remaining_duration_min、reason；
- client_event_id 用于幂等，避免重复点击导致时长被重复扣减。

## 五、周规划状态

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

## 六、五个核心节点

### 1. UnderstandWeek

识别目标、总时长、DDL、优先级、可拆分性、阶段和依赖；只追问会显著改变计划的关键缺口。记忆不能覆盖本轮要求。

### 2. BuildCapacity

展开七天课表、固定日程和校历覆盖，计算自由时间窗，并附加精力时段、拥堵、天气和场馆限制。超出可靠预报范围的天气只标记不确定性。

### 3. AllocateWeek

按硬截止风险、依赖深度、剩余时长和重要度排序；从截止时间向前分配；遵守分块规则和每日负担上限；尽量聚合同地点任务。首版使用确定性启发式，必要时再引入 CP-SAT。

### 4. GroundDays

把每个 DayAllocation 转换为现有 Task，调用日规划器加入路线、拥堵、天气、开放时间和缓冲。某天不可行时，返回失败块和替代容量；每日最多修复两次。

### 5. RepairAndRespond

冻结已完成、已开始和用户锁定内容，只重排受影响的剩余任务；计算保留率、延期风险和新旧差异；输出自然、关怀且可执行的说明。

## 七、硬约束和软目标

硬约束：

- 固定课程与活动不可移动；
- 阶段依赖不能逆序；
- 硬截止不能突破；
- 场馆关闭时不能安排；
- 日计划不能重叠；
- 跨地点必须留出通勤；
- 锁定任务不能移动；
- 已完成任务不能重写。

软目标依次优化：

- 截止风险；
- 原计划移动量；
- 每日负担不均衡；
- 总通勤时间；
- 任务碎片化；
- 偏好违背程度。

如果客观不可行，正确行为是返回 at_risk 或 infeasible，精确说明缺少多少分钟和冲突来源，并给出不超过两个可执行选择。

## 八、API

- `POST /api/v1/weeks/plan`：生成周计划；
- `GET /api/v1/weeks/{week_start}`：查询周计划；
- `POST /api/v1/weeks/{plan_id}/events`：记录完成、部分完成、跳过或新增任务；
- `POST /api/v1/weeks/{plan_id}/replan`：滚动重排；
- `PATCH /api/v1/weeks/{plan_id}/allocations/{allocation_id}`：锁定、解锁、改时长和状态。

SQLite 新增：

- weekly_goals；
- goal_stages；
- weekly_plans；
- day_allocations；
- completion_events；
- weekly_plan_versions。

每次重排保存新版本，不覆盖旧版本，以便展示差异和计算保留率。

## 九、前端

首版只展示对用户有用的四块：

1. 本周目标：进度、剩余时长、DDL 风险；
2. 七日概览：每天任务块、固定课程和负担等级；
3. 今天怎么做：复用现有详细时间轴；
4. 变化说明：哪些任务移动了、为什么、保留率多少。

支持完成、部分完成、今天没做、锁定、延后、新增任务和局部重排。内部英文变量、数据库 ID、节点名和模型原始 JSON 默认隐藏。

## 十、个性化边界

- 用户主动开启后才识别重复行为；
- 只询问是否加入，不自动写入计划；
- 拒绝一次后冷却，连续拒绝两次后停止主动建议；
- 用户可关闭总开关；
- 习惯不得覆盖课表、DDL、开放时间和本轮要求；
- 不同学校和校区的地点习惯隔离。

## 十一、跨学校适用

核心规划算法不绑定杭电。不同学校通过 Campus Profile 提供学校/校区、节次、学期和教学周、场馆时间、学校校历、规章知识库、高德校园地点和天气编码。

未导入某校规则时，系统只能使用该校高德地点、路线和天气，不得借用其他学校的节次或开放规则。

## 十二、测试与指标

三个固定 fixture：

1. weekly_01_multi_deadline：多 DDL、阶段拆分和运动分散；
2. weekly_02_rollover：未完成任务滚动，保留锁定安排；
3. weekly_03_weather_and_class_change：天气与临时加课共同触发局部重排。

首版验收：

| 指标 | 目标 |
|---|---:|
| 硬约束违反率 | 0% |
| 阶段依赖正确率 | 100% |
| 硬截止满足率 | ≥95%（客观可行样本） |
| 日计划可执行率 | ≥95% |
| 滚动重排成功率 | ≥90% |
| 原计划保留率 | ≥75% |
| 完成事件幂等率 | 100% |
| 跨学校规则串用率 | 0% |

## 十三、开发阶段

A. 数据模型、SQLite 表、repository、幂等和版本测试。  
B. 确定性周分配器、每日容量、DDL/分块/依赖。  
C. 调用现有日规划器并实现滚动修复。  
D. 周视图和完成/锁定操作。  
E. 第二所学校实测、三个 fixture 和参赛指标。

首版冻结：多智能体辩论、强化学习、自动读取教务账号、后台无限自主运行、团队排程和七天以上项目管理。

## 十四、参赛表达

> 易程智策不仅回答“今天怎么排”，还能够把跨日目标拆成可执行阶段，结合课表、校园规则、通勤和天气形成一周计划，并在临时变化发生后以最小扰动方式滚动调整。

该方向具备可演示性、可量化性、可实现性和跨学校普遍性。
