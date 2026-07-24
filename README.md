# 易程智策

面向大学生学习生活的校园时空规划智能体。

系统使用 LangGraph 组织“需求理解 → 校园信息补全 → 日程规划 →
硬约束校验 → 结果输出”五步流程，以 FastAPI 提供网页和接口。千问负责
自然语言理解，Python 负责时间计算、排程与校验，高德提供实时步行路线和
天气，校园知识库提供制度与服务规则。

## 当前状态

- 模型容错链：主模型不可用或额度耗尽时自动切换备用千问模型，
  全部在线模型不可用时继续使用本地确定性解析；
- 高德路线与天气：已真实联调；
- 校园知识库：206 页学生手册 + 已核验校园服务时间知识；
- 校园知识分块：约 97 个；
- 检索：查询扩展 + 来源分级 + 二阶段重排去重；
- 长期记忆：SQLite 持久化，支持前端增改、启停和删除；
- 课程节次：用户声明后按已核验作息锁定为硬约束；
- 自动化测试：108 项通过；
- 离线评估：60/60 通过；
- 三个固定 Demo：全部通过；
- 真实端到端响应：7.17 秒、0 个硬约束错误、0 个告警；
- 运行范围：本地版本与 Vercel 公网版本均可直接运行。

## 本地启动

双击：

```text
启动易程智策.command
```

或执行：

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问：

- 应用：<http://127.0.0.1:8000/>
- 接口文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

`localhost` 仅供开发，不可作为参赛应用入口。

## 外部服务配置

密钥仅保存在 `.env`，禁止提交或截图。当前推荐配置：

```dotenv
LLM_ENABLED=true
LLM_MODEL=qwen3.6-flash
LLM_FALLBACK_MODELS=qwen3.7-plus,qwen-plus-2025-07-28
LLM_ENABLE_THINKING=false
LLM_RENDER_ENABLED=true
LLM_TIMEOUT_SECONDS=10

LIVE_ROUTE_ENABLED=true
LIVE_WEATHER_ENABLED=true
```

高德天气城市编码默认从 `data/campus_profile.json` 读取。模型、路线或天气
失败时，系统依次切换备用模型、本地解析和静态数据，不阻断核心规划。

## 验收

```bash
.venv/bin/python scripts/validate_static_data.py
.venv/bin/pytest -q
.venv/bin/python scripts/run_evaluation.py
.venv/bin/python scripts/demo_smoke.py
```

真实接口检查：

```bash
.venv/bin/python scripts/live_llm_smoke.py
.venv/bin/python scripts/live_amap_smoke.py
.venv/bin/python scripts/live_end_to_end_smoke.py
```

这些脚本不会打印 API Key。

## 可替换校园配置

学校差异集中在 `data/`：

```text
campus_profile.json
locations.json
travel_times.json
opening_hours.json
campus_rules.json
class_periods.json
knowledge/
```

切换其他高校时，通过 `APP_DATA_DIR` 指向另一套 Campus Profile。只替换
学生手册可迁移制度问答；完整时空规划还需要该校地点、开放时间、节次和
路线数据。

## 文档

- 当前交付状态：[`docs/plans/项目交付清单与待办.md`](docs/plans/项目交付清单与待办.md)
- 完整工程方案：[`docs/plans/新版工程执行计划.md`](docs/plans/新版工程执行计划.md)
- 校园配置：[`docs/CAMPUS_PROFILE.md`](docs/CAMPUS_PROFILE.md)
- 环境：[`docs/environment.md`](docs/environment.md)
- API：[`docs/api.md`](docs/api.md)
- 演示：[`docs/demo_script.md`](docs/demo_script.md)
- 部署：[`docs/deployment.md`](docs/deployment.md)
- 发布检查：[`reports/release_checklist.md`](reports/release_checklist.md)
- 评估报告：[`reports/evaluation.md`](reports/evaluation.md)
