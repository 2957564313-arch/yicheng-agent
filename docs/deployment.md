# 部署说明

## 比赛版部署原则

- 单实例 FastAPI；
- Python 3.12；
- 正式版数据库使用持久化存储；
- HTTPS 由反向代理或托管平台提供；
- 固定 Demo 默认离线，普通输入使用实时增强；
- 密钥只通过环境变量注入，禁止写进仓库；
- 每次发布前备份 `runtime/app.db`。

## Vercel 预览版

仓库根目录的 `server.py` 是 Vercel 识别 FastAPI 应用的入口。Vercel
运行时只允许把临时文件写到 `/tmp`，因此预览版会把 SQLite 数据库放在
`/tmp/yicheng-agent/`。这种数据会在冷启动、实例切换或重新部署后丢失，
只适合公开体验和功能测试，不应作为长期记忆的最终存储。

Vercel 预览版无需配置额外启动命令。导入 GitHub 仓库后，框架保持自动
识别，根目录保持仓库根目录。首次部署可以先不开启外部 API，确认首页、
健康检查和三个离线 Demo 均可访问，再配置模型、高德路线和天气环境变量。

需要长期保存计划、记忆和跨学校配置时，应把 SQLite 迁移到 PostgreSQL；
学校知识文件应迁移到对象存储，并按 `campus_id` 隔离。

## 启动命令

```bash
uv sync --frozen
uv run python -m scripts.init_db
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

生产环境建议由进程管理器托管，并配置启动失败重试。当前 SQLite 方案只适合
单应用实例；在迁移 PostgreSQL 之前，禁止横向启动多个写入实例。

## 必需持久化目录

- `runtime/app.db`：用户、对话、计划和运行记录；
- `runtime/checkpoints.db`：智能体状态检查点；
- `data/knowledge/`：导入并核验后的知识文档。

## 环境变量

离线应急版：

```dotenv
LLM_ENABLED=false
LIVE_ROUTE_ENABLED=false
LIVE_WEATHER_ENABLED=false
```

公网实时版：

```dotenv
LLM_ENABLED=true
LLM_MODEL=qwen3.6-flash
LLM_FALLBACK_MODELS=qwen3.7-plus,qwen-plus-2025-07-28
LLM_BASE_URL=<百炼 OpenAI 兼容地址>
LLM_API_KEY=<服务器密钥>
LLM_ENABLE_THINKING=false
LLM_RENDER_ENABLED=true
LLM_TIMEOUT_SECONDS=10

LIVE_ROUTE_ENABLED=true
ROUTE_API_KEY=<高德 Web 服务 Key>
ROUTE_TIMEOUT_SECONDS=3

LIVE_WEATHER_ENABLED=true
WEATHER_API_KEY=<高德 Web 服务 Key>
WEATHER_TIMEOUT_SECONDS=3
```

`WEATHER_CITY_ADCODE` 可以留空，默认从当前 Campus Profile 读取。

实时增强版必须同时满足以下条件：

- 模型：兼容接口已用结构化输出案例验证；
- 模型容错：主模型额度耗尽、限流或不可用时能切换备用模型；
- 路线：地点真实坐标已核验，Web 服务 Key 可用；
- 天气：城市 adcode 已核验，返回字段完成联调。

当前比赛版入口默认无需登录。提交信息表的测试账号栏填写“无需账号，访问
链接即可体验”。如部署平台自身增加了访问保护，应填写平台提供的独立测试
账号，不要把管理员账号交给评审。

## 高德配额与公网 IP

- 确认高德账户完成个人开发者认证；
- 比赛版本不要购买额外流量包；
- 路线请求已按个人账户每秒 3 次限制进行节流；
- 地点坐标和七组核心路线已本地固化；
- 天气与路线失败时会自动降级；
- 服务器具有固定出口 IP 后，可以把该 IP 加入高德 Key 白名单；
- 若托管平台出口 IP 不固定，暂不配置 IP 白名单，但必须保管好 Key。

## 当前待选平台

公网平台尚未确定。选择时必须同时满足：

- 能运行 Python 3.12 和 FastAPI；
- 能配置环境变量；
- 能挂载持久化磁盘；
- 能提供 HTTPS；
- 能长期运行单实例服务；
- 能从中国大陆稳定访问百炼和高德；
- 能提供固定或可查的公网地址。

不能把纯静态网页托管当作完整部署，因为模型、SQLite、RAG、地图和天气均
运行在服务端。

## 发布流程

1. 冻结需求，不在发布当天新增功能；
2. 运行静态数据校验；
3. 运行全部 60 项自动化测试；
4. 运行 60 例评估；
5. 本地浏览器运行三个 Demo；
6. 备份数据库；
7. 发布；
8. 在生产 URL 再运行三个 Demo；
9. 在生产 URL 运行真实端到端案例；
10. 生成二维码并更新 PPT；
11. 记录版本号、提交号、测试时间和负责人。

## 回滚

保留上一版完整代码包、锁文件和数据库备份。新版本出现以下任一情况立即
回滚：

- 健康检查失败；
- 三个比赛 Demo 中任意一个无法生成有效计划；
- 数据库写入错误；
- 响应泄露密钥或内部异常；
- 核心接口连续三次超时。
