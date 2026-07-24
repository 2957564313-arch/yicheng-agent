# 数据字典

## 统一任务 Task

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 单次请求内唯一任务 ID |
| `title` | string | 用户可读任务名 |
| `date` | date | 目标日期 |
| `duration_min` | int | 5—720 分钟 |
| `location_id` | string/null | 标准地点 ID |
| `location_raw` | string/null | 用户原始地点表达 |
| `earliest_start` | datetime/null | 最早开始时间 |
| `latest_end` | datetime/null | 最晚结束时间 |
| `fixed_start` / `fixed_end` | datetime/null | 固定任务时间 |
| `deadline` | datetime/null | 完成截止时间 |
| `flexibility` | enum | `fixed` / `movable` / `locked` |
| `importance` | int | 1—5 |
| `preferred_period` | string/null | 上午、下午、晚上等偏好 |
| `depends_on` | string[] | 前置任务 ID |
| `tags` | string[] | 任务标签 |

所有 datetime 必须含时区。`fixed` 和 `locked` 任务必须同时具有
`fixed_start`、`fixed_end`，且时长与 `duration_min` 一致。

`UserPreferences.transport_mode` 取值为 `walk`、`bicycle` 或
`electrobike`。用户未说明时默认步行；本轮明确出行方式优先于长期记忆。
`avoid_congestion` 只是错峰软偏好，不得覆盖固定课程、任务顺序和截止
时间。

## 统一状态 CampusAgentState

状态只在服务内部流转，按五个节点逐步补全：

1. `understand` 写入 `intent`、`requested_date`、`tasks`、
   `preferences`、`clarifications`；
2. `enrich` 写入 `normalized_locations`、`travel_estimates`、
   `congestion_windows`、`weather_context`、`retrieved_facts`、
   `opening_windows`；
3. `plan` 写入 `candidate_plan`、`planner_diagnostics`；
4. `validate` 写入 `validation_issues`；
5. `respond` 写入 `final_plan`、`final_answer`、
   `response_warnings`。

追踪字段 `request_id`、`trace_id`、`node_trace` 贯穿全链路。

## 当前计划与计划差异

- `plans` 只保存通过校验的 `valid` 计划；
- 调整类请求优先使用显式 `old_plan_id`，否则读取同一 `thread_id` 的
  最近有效计划；
- `previous_plan` 是本次调整的基准；
- `plan_diff` 按 `task_id` 比较任务开始时间、结束时间和持续时长；
- 自动插入的 travel item 不计为用户任务变化；
- 不可行结果不会覆盖当前计划。

## 计划 Plan

`PlanItem.item_type`：

- `task`：用户任务；
- `travel`：跨地点通勤；
- `buffer`：显式缓冲；
- `meal`：显式用餐。

`Plan.status`：

- `draft`：待校验；
- `valid`：通过全部硬约束；
- `infeasible`：达到最大重规划次数后仍存在硬错误。

## 静态地点 locations.json

```json
{
  "schema_version": "1.0",
  "campus_id": "campus_id",
  "data_quality": "verified",
  "updated_at": "2026-07-23T00:00:00+08:00",
  "locations": [
    {
      "id": "library",
      "name": "图书馆",
      "aliases": ["校图书馆"],
      "category": "study",
      "longitude": 120.0,
      "latitude": 30.0,
      "zone": "teaching_area",
      "source": {
        "type": "official",
        "reference": "来源链接或文件",
        "verified_at": "2026-07-23"
      }
    }
  ]
}
```

只有在名称、别名、坐标和来源全部复核后，才可把 `data_quality`
改成 `verified`。

## 通勤矩阵 travel_times.json

每条记录必须包含起终点、方式、分钟、数据来源和置信度。矩阵按有向边
读取，不能默认往返耗时完全相同。缺边时，排程器会记录
`missing_route_pairs`，不会凭空生成通勤时间。

在线模式默认调用高德步行路线；用户明确选择自行车或电瓶车时分别调用
高德骑行、电动车路线。高德结果是 `base_duration_min`。若实际出发时间
与 `class_periods.json` 中的拥堵窗口重叠，规划器必须在基础时间上加入
`congestion_delay_min`，扩展后的通勤时间参与时间窗、固定课程和截止
时间校验。拥堵本身不是禁止通行的硬约束：系统可以建议错峰，但只有用户
接受后才将错峰作为软优化目标。

时间约束优先级最高。校验器必须同时检查固定任务时间、最早开始、最晚
结束、截止时间、任务重叠、场所开放时间以及加入高峰缓冲后的通勤时间。

## 开放时间 opening_hours.json

开放时间属于硬约束，优先级高于知识库文本。需要记录适用星期、日期例外、
时区、来源和核验日期。节假日或临时闭馆信息没有可靠来源时，不得作为
确定事实。

## 知识库

知识文件存放在 `data/knowledge/`。由压缩包导入的文档包含：

```yaml
source_archive: coze.zip
source_path: 压缩包中的原路径
imported_at: 导入时间
verified: false
```

知识检索采用“查询扩展召回 → 精确短语、核验状态和来源层级重排 →
相似段落去重”的本地增强流程。它负责提供制度与服务依据，不替代确定性
排程。硬约束优先级依次为：

1. 用户本轮明确输入；
2. 已核验结构化数据；
3. 实时且成功的外部接口；
4. 已核验知识库文档；
5. 未核验文档和演示数据。

低优先级来源不得覆盖高优先级来源。

本地检索会剥离 Markdown front matter，不把导入路径等元数据当成知识正文。
未核验文档的检索优先级被限制在较低区间，并在 metadata 中保留
`verified: false`。

## 长期记忆

`user_memories` 保存用户主动设置并可手动管理的偏好与习惯。启用的记忆
可跨会话参与规划；停用或删除后不再生效。记忆永远是软偏好，不得覆盖
本轮明确要求、课程节次、开放时间、截止时间和实时安全信息。
