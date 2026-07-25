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
- 校园知识分块：109 个；
- 检索：按规划/制度问答分域 + 查询扩展 + 来源分级 + 二阶段重排去重；
- 长期记忆：SQLite 持久化，支持前端增改、启停和删除；
- 个人课表：支持杭电 PDF 预览确认，以及通用 Excel、CSV、JSON 导入；
- 学期映射：按第一教学周周一换算周次、单双周和真实上课日期；
- 校历约束：法定节假日、调休工作日与学校补课/停课分层处理；
- 课程节次：个人课表和用户语言描述都会按已核验作息锁定为硬约束；
- 跨校地点：可输入学校/校区，按六类从高德发现并保存本校地点目录；
- 校园隔离：地点、路线、天气和规则按 `campus_id` 隔离，禁止跨校兜底；
- 个性化建议：用户主动开启后才识别重复行为，只征求确认、不自动加任务，
  支持忽略冷却、重复拒绝降频和手动重置；
- 测试入口保护：可选固定测试账号登录，高成本接口使用短期签名凭证；
- 自动化测试：141 项通过；
- 离线评估：60/60 通过；
- 端到端场景：25/25 通过；
- 连续状态场景：10/10 通过；
- 三个固定 Demo：全部通过；
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
APP_ACCESS_ENABLED=false
APP_TEST_USERNAME=
APP_TEST_PASSWORD=
APP_AUTH_SECRET=
APP_ACCESS_HOURS=8

LLM_ENABLED=true
LLM_MODEL=qwen3.7-plus
LLM_FALLBACK_MODELS=qwen-plus-2025-07-28,glm-5
LLM_ENABLE_THINKING=false
LLM_RENDER_ENABLED=true
LLM_PLAN_RENDER_ENABLED=false
LLM_TIMEOUT_SECONDS=10

LIVE_ROUTE_ENABLED=true
LIVE_WEATHER_ENABLED=true
```

高德天气城市编码默认从当前校园配置读取。模型不可用时依次切换备用模型
和本地解析；路线接口失败时，只能根据当前学校已发现并缓存的地点坐标保守
估算，绝不会借用其他学校的地点或路线；天气没有可靠来源时明确标记未知。

## 验收

```bash
.venv/bin/python scripts/validate_static_data.py
.venv/bin/pytest -q
.venv/bin/python scripts/run_evaluation.py
.venv/bin/python scripts/demo_smoke.py
node scripts/public_acceptance.mjs
node scripts/public_stateful_acceptance.mjs
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

公开页面可输入其他学校或校区，自动从高德建立该校地点目录，并据此查询
路线和天气。地点目录不等于完整知识包：只替换学生手册可迁移制度问答；
要让开放时间、课程节次和校历参与硬约束，还需要导入该校对应的 Campus
Profile。未导入时系统会明确提示，并禁止借用默认学校规则。

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
