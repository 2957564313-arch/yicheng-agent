# 需求追踪

> 当前状态以自动化测试和三个固定 Demo 为准。

| ID | 需求 | 新版模块 | 对应测试 | 状态 |
|---|---|---|---|---|
| REQ-001 | 解析口语化校园任务 | understand | schema / demo API / evaluation | implemented |
| REQ-002 | 同时考虑时间、地点和通勤 | enrich / plan | scheduler / static providers | implemented |
| REQ-003 | 检查重叠、DDL、开放时间和任务遗漏 | validate | validator / demo API | implemented |
| REQ-004 | 突发变化时进行最小扰动调整 | plan | replanner / emergency demo | implemented |
| REQ-005 | 地图或天气失败时仍可生成计划 | enrich | fallback providers / degraded demo | implemented |
| REQ-006 | 提供可直接体验的网页入口 | web / api | browser smoke test / API integration | implemented |
| REQ-007 | 保存通过校验的当前计划 | repository / chat | demo API / database | verified |
| REQ-008 | 展示调整前后计划差异和原因 | plan diff / web | plan diff / demo API | verified |
| REQ-009 | 天气风险应改变室外任务安排 | plan / validate | weather demo | verified |
| REQ-010 | 展示五步执行状态和硬约束结果 | chat / web | demo API | verified |
| REQ-011 | 一键复位比赛演示状态 | demo API / web | reset integration | verified |

“verified”表示已有固定验收用例；“implemented”表示能力已实现但仍应继续
扩充边界测试。模型、地图和天气的实时增强能力只有在配置密钥、补齐已核验
地点坐标并完成联调后，才能标记为 production-verified。
