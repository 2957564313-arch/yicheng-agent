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
- 校园知识分块：370 个，按 PDF 页码和页内章节切分，避免跨章节串证据；
- 检索：按规划/制度问答分域 + 同义问法归一 + 查询扩展 + 来源分级 +
  候选召回/二阶段重排 + 数值答案优先 + 相似证据去重；
- 检索证据：学生手册回答可追溯到原文件、页码和章节；
- 长期记忆：支持前端增改、启停和删除，并可随个人数据包跨设备恢复；
- 个人课表：每位用户可导入自己的杭电课表 PDF，也可使用 Excel、CSV、JSON；
- 学期映射：按第一教学周周一换算周次、单双周和真实上课日期；
- 校历约束：法定节假日、调休工作日与学校补课/停课分层处理；
- 课程节次：个人课表和用户语言描述都会按已核验作息锁定为硬约束；
- 本校知识底座：深入使用杭电节次、场馆、门禁、快递、长跑、医院、拥堵和学生手册；
- 个性化数据：个人课表、长期偏好、常用地点和完成反馈由用户独立管理；
- 个性化建议：用户主动开启后才识别重复行为，只征求确认、不自动加任务，
  支持忽略冷却、重复拒绝降频和手动重置；
- 作息关怀：按用户维护的就寝、起床时间与睡眠目标生成提醒，结合次日早课
  和晚间安排提示作息冲突，并支持单独关闭；
- 提醒落地：网页打开时可使用浏览器通知；导出的 90 天系统日历包含课程、
  会议、学习和就寝闹钟，关闭网页后由手机或电脑系统日历继续提醒；
- 个人数据迁移：一键备份和恢复课表、长期记忆、校历调整、提醒设置、
  当前计划及个性化习惯，不导出密码、登录凭证或 API 密钥；
- 公网个人上下文：日程汇总、到点提醒和系统日历导出会携带当前浏览器的
  课表、记忆、校历、提醒设置与计划快照；即使连续请求落到不同的 Vercel
  临时实例，也不会因为实例切换漏掉个人数据；
- 测试入口保护：可选固定测试账号登录，高成本接口使用短期签名凭证；
- 周规划自然语言入口：可直接描述多个目标、总时长、阶段依赖、重复次数、
  截止时间、偏好时段和地点；信息不够时先追问；
- 自动化测试：251 项通过；
- 真实知识库检索验收：36/36 通过，覆盖校园服务时间和学生手册制度；
- 离线评估：100/100 通过，覆盖知识问答、时间硬约束与关怀韧性；
- 端到端场景：32/32 通过；
- 连续状态场景：15/15 通过；
- 产品级公网旅程：8/8 通过；
- 三个固定 Demo：全部通过；
- 运行范围：本地版本与 Vercel 公网版本均可直接运行。

公网测试入口：<https://yicheng-agent.vercel.app/>

入口二维码：

![易程智策公网入口二维码](app/web/assets/yicheng-public-entry.png)

当前 Vercel 版本用于跨网络体验和比赛测试。个人课表、记忆、提醒设置会在
浏览器本机保留快照，每次长期日程请求都会使用该快照重建当前执行上下文，
并可导出个人数据包迁移到新设备；正式长期运营前仍需迁移到具备持久化
数据库的国内服务器。

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
估算，且不会采用校园范围外的同名地点；天气没有可靠来源时明确标记未知。

## 验收

```bash
.venv/bin/python scripts/validate_static_data.py
.venv/bin/pytest -q
.venv/bin/python scripts/run_evaluation.py
.venv/bin/python scripts/demo_smoke.py
node scripts/public_acceptance.mjs
node scripts/public_stateful_acceptance.mjs
node scripts/public_product_acceptance.mjs
```

真实接口检查：

```bash
.venv/bin/python scripts/live_llm_smoke.py
.venv/bin/python scripts/live_amap_smoke.py
.venv/bin/python scripts/live_end_to_end_smoke.py
```

这些脚本不会打印 API Key。

## 杭电知识配置

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

当前公开页面固定使用杭州电子科技大学下沙校区知识库，并据此查询路线和
天气。上述文件共同提供本校地点、课程节次、开放时间、活动有效时段、
校园拥堵和学生手册依据。个人课表、长期偏好和完成记录则按用户分别保存，
不会写入学校公共知识。

## 文档

- PPT 当前实测数据：[`docs/易程智策_当前工程与PPT实测数据.md`](docs/易程智策_当前工程与PPT实测数据.md)
- 当前交付状态：[`docs/plans/项目交付清单与待办.md`](docs/plans/项目交付清单与待办.md)
- 完整工程方案：[`docs/plans/新版工程执行计划.md`](docs/plans/新版工程执行计划.md)
- 周规划与滚动重排：[`docs/WEEKLY_PLANNING.md`](docs/WEEKLY_PLANNING.md)
- RAG 验收：[`reports/rag_acceptance.md`](reports/rag_acceptance.md)
- 队友方案吸收记录：[`reports/teammate_integration_review.md`](reports/teammate_integration_review.md)
- 本校知识底座：[`docs/CAMPUS_PROFILE.md`](docs/CAMPUS_PROFILE.md)
- 环境：[`docs/environment.md`](docs/environment.md)
- API：[`docs/api.md`](docs/api.md)
- 演示：[`docs/demo_script.md`](docs/demo_script.md)
- 部署：[`docs/deployment.md`](docs/deployment.md)
- 发布检查：[`reports/release_checklist.md`](reports/release_checklist.md)
- 评估报告：[`reports/evaluation.md`](reports/evaluation.md)
- 公网产品验收：[`reports/product_acceptance.md`](reports/product_acceptance.md)
- 公网入口二维码：[`app/web/assets/yicheng-public-entry.png`](app/web/assets/yicheng-public-entry.png)
