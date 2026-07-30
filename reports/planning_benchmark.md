# 易程智策确定性规划基线与消融报告

- 冻结数据版本：`2026.07.29-v1`
- 场景数量：24
- 固定随机种子：`20260729`
- 数据 SHA256：`ee8a013111212982d83080c94a43b69377b3e053eb7aeb0147414da748356e5f`
- 联网或大模型调用：无

## 汇总

| 方法 | 可行完成率 | 硬约束违反 | 截止满足率 | 保留率 | 误移动率 | 总位移（分钟） |
|---|---:|---:|---:|---:|---:|---:|
| 贪心最早插入基线 | 33.3% | 19 | 50.0% | 2.8% | 95.5% | 9755 |
| 约束排程（关闭历史） | 100.0% | 0 | 100.0% | 2.8% | 95.5% | 9155 |
| 完整策略（最小扰动） | 100.0% | 0 | 100.0% | 72.2% | 0.0% | 1035 |

## 方法边界

24个冻结的合成校园日程场景，用于比较通用最早插入、当前约束排程，以及关闭/开启旧计划历史后的最小扰动差异。

该报告不是用户研究，也不包含任何虚构的大模型结果。它只证明冻结输入下三个确定性算法的可复现行为。

## 算法定义

- `greedy_first_fit`：按输入顺序把任务放入最早的非重叠五分钟时隙；只处理固定时间、最早开始、最晚结束和截止时间，不读取路线、场馆、天气、依赖或旧计划。
- `constraint_scheduler_no_history`：使用当前确定性约束排程器，但在重排案例中移除旧计划历史；这是“关闭最小扰动目标”的消融组。
- `constraint_scheduler_min_disruption`：完整当前策略：约束排程与校验；重排案例额外使用旧计划位移成本，并保留锁定任务。

## 分场景结果

### 贪心最早插入基线

| 场景 | 类别 | 可行完成 | 硬约束违反 | 误移动 | 位移分钟 |
|---|---|---:|---:|---:|---:|
| `P01_deadline_priority` | deadline | 否 | 1 | 0 | 0 |
| `P02_fixed_course_control` | control | 是 | 0 | 0 | 0 |
| `P03_route_buffer` | travel | 否 | 1 | 0 | 0 |
| `P04_venue_opening` | opening_hours | 否 | 1 | 0 | 0 |
| `P05_activity_window` | activity_window | 否 | 1 | 0 | 0 |
| `P06_weather_reordering` | weather | 否 | 1 | 0 | 0 |
| `P07_congestion_route` | congestion | 否 | 1 | 0 | 0 |
| `P08_dependency_pair` | dependency | 否 | 1 | 0 | 0 |
| `P09_dependency_chain` | dependency | 否 | 2 | 0 | 0 |
| `P10_multi_stop_travel` | travel | 否 | 2 | 0 | 0 |
| `P11_competing_deadlines` | deadline | 否 | 2 | 0 | 0 |
| `P12_basic_control` | control | 是 | 0 | 0 | 0 |
| `R01_class_insertion` | minimal_disruption | 是 | 0 | 2 | 900 |
| `R02_morning_meeting` | minimal_disruption | 是 | 0 | 2 | 840 |
| `R03_opening_delayed` | opening_hours | 否 | 1 | 2 | 840 |
| `R04_rain_boundary` | weather | 是 | 0 | 2 | 1035 |
| `R05_new_urgent_task` | deadline | 否 | 1 | 3 | 900 |
| `R06_duration_expansion` | minimal_disruption | 是 | 0 | 2 | 720 |
| `R07_activity_window_shift` | activity_window | 否 | 1 | 2 | 900 |
| `R08_route_time_changed` | travel | 否 | 1 | 1 | 740 |
| `R09_congestion_changed` | congestion | 否 | 1 | 1 | 660 |
| `R10_dependency_changed` | dependency | 否 | 1 | 1 | 900 |
| `R11_locked_task` | locked_task | 是 | 0 | 1 | 420 |
| `R12_two_fixed_events` | minimal_disruption | 是 | 0 | 2 | 900 |

### 约束排程（关闭历史）

| 场景 | 类别 | 可行完成 | 硬约束违反 | 误移动 | 位移分钟 |
|---|---|---:|---:|---:|---:|
| `P01_deadline_priority` | deadline | 是 | 0 | 0 | 0 |
| `P02_fixed_course_control` | control | 是 | 0 | 0 | 0 |
| `P03_route_buffer` | travel | 是 | 0 | 0 | 0 |
| `P04_venue_opening` | opening_hours | 是 | 0 | 0 | 0 |
| `P05_activity_window` | activity_window | 是 | 0 | 0 | 0 |
| `P06_weather_reordering` | weather | 是 | 0 | 0 | 0 |
| `P07_congestion_route` | congestion | 是 | 0 | 0 | 0 |
| `P08_dependency_pair` | dependency | 是 | 0 | 0 | 0 |
| `P09_dependency_chain` | dependency | 是 | 0 | 0 | 0 |
| `P10_multi_stop_travel` | travel | 是 | 0 | 0 | 0 |
| `P11_competing_deadlines` | deadline | 是 | 0 | 0 | 0 |
| `P12_basic_control` | control | 是 | 0 | 0 | 0 |
| `R01_class_insertion` | minimal_disruption | 是 | 0 | 2 | 870 |
| `R02_morning_meeting` | minimal_disruption | 是 | 0 | 2 | 630 |
| `R03_opening_delayed` | opening_hours | 是 | 0 | 2 | 1070 |
| `R04_rain_boundary` | weather | 是 | 0 | 2 | 1015 |
| `R05_new_urgent_task` | deadline | 是 | 0 | 3 | 750 |
| `R06_duration_expansion` | minimal_disruption | 是 | 0 | 2 | 710 |
| `R07_activity_window_shift` | activity_window | 是 | 0 | 2 | 710 |
| `R08_route_time_changed` | travel | 是 | 0 | 1 | 650 |
| `R09_congestion_changed` | congestion | 是 | 0 | 1 | 600 |
| `R10_dependency_changed` | dependency | 是 | 0 | 1 | 870 |
| `R11_locked_task` | locked_task | 是 | 0 | 1 | 410 |
| `R12_two_fixed_events` | minimal_disruption | 是 | 0 | 2 | 870 |

### 完整策略（最小扰动）

| 场景 | 类别 | 可行完成 | 硬约束违反 | 误移动 | 位移分钟 |
|---|---|---:|---:|---:|---:|
| `P01_deadline_priority` | deadline | 是 | 0 | 0 | 0 |
| `P02_fixed_course_control` | control | 是 | 0 | 0 | 0 |
| `P03_route_buffer` | travel | 是 | 0 | 0 | 0 |
| `P04_venue_opening` | opening_hours | 是 | 0 | 0 | 0 |
| `P05_activity_window` | activity_window | 是 | 0 | 0 | 0 |
| `P06_weather_reordering` | weather | 是 | 0 | 0 | 0 |
| `P07_congestion_route` | congestion | 是 | 0 | 0 | 0 |
| `P08_dependency_pair` | dependency | 是 | 0 | 0 | 0 |
| `P09_dependency_chain` | dependency | 是 | 0 | 0 | 0 |
| `P10_multi_stop_travel` | travel | 是 | 0 | 0 | 0 |
| `P11_competing_deadlines` | deadline | 是 | 0 | 0 | 0 |
| `P12_basic_control` | control | 是 | 0 | 0 | 0 |
| `R01_class_insertion` | minimal_disruption | 是 | 0 | 0 | 70 |
| `R02_morning_meeting` | minimal_disruption | 是 | 0 | 0 | 70 |
| `R03_opening_delayed` | opening_hours | 是 | 0 | 0 | 180 |
| `R04_rain_boundary` | weather | 是 | 0 | 0 | 175 |
| `R05_new_urgent_task` | deadline | 是 | 0 | 0 | 0 |
| `R06_duration_expansion` | minimal_disruption | 是 | 0 | 0 | 0 |
| `R07_activity_window_shift` | activity_window | 是 | 0 | 0 | 60 |
| `R08_route_time_changed` | travel | 是 | 0 | 0 | 20 |
| `R09_congestion_changed` | congestion | 是 | 0 | 0 | 10 |
| `R10_dependency_changed` | dependency | 是 | 0 | 0 | 310 |
| `R11_locked_task` | locked_task | 是 | 0 | 0 | 70 |
| `R12_two_fixed_events` | minimal_disruption | 是 | 0 | 0 | 70 |

## 局限

- 这些是可审计的确定性合成场景，不代表真实用户满意度或真实世界分布。
- 基准不调用大模型、地图或天气网络接口，因此不能替代线上端到端验收。
- 误移动仅针对每个重排案例明确标注、且原时段仍应保留的 unaffected_task_ids。
- 结果适合证明算法行为和回归稳定性，不应包装成真人试用结果。
