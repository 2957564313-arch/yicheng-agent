# 部署说明

## 比赛版部署原则

- 单实例 FastAPI；
- Python 3.12；
- 正式版数据库使用持久化存储；
- HTTPS 由反向代理或托管平台提供；
- 固定 Demo 使用冻结数据快照保证可复现，普通输入默认使用实时增强；
- 密钥只通过环境变量注入，禁止写进仓库；
- 每次发布前备份 `runtime/app.db`。

## 当前生产部署：Cloudflare + Alibaba ECS

当前公网入口为 <https://yichengapp.top/>，生产链路为：

```text
Cloudflare DNS/代理 → Caddy HTTPS → systemd → FastAPI 127.0.0.1:8000
```

- 域名：`yichengapp.top`；`www.yichengapp.top` 永久重定向到根域名；
- 服务目录：`/srv/yicheng-agent`；
- 持久化数据：`/srv/yicheng-agent/runtime/`；
- 服务名：`yicheng-agent.service`；
- 健康检查：`https://yichengapp.top/api/v1/health`；
- 发布来源：GitHub `main` 分支，当前不从其他分支直接上线。

服务器上的 `/usr/local/sbin/yicheng-deploy` 会执行以下动作：拉取
`origin/main`、同步锁定依赖、保留 `.env` 和 `runtime/`、重启服务并等待
健康检查成功。执行命令：

```powershell
ssh -i 'D:\key\yicheng-ecs-2026.pem' `
  ecs-user@120.26.65.5 "sudo /usr/local/sbin/yicheng-deploy"
```

首次部署或更换服务器时，必须先配置 GitHub 仓库 Deploy key、Cloudflare
DNS 和 ECS 安全组的 80/443 端口；SSH 仅用于维护，不应在 README、PPT 或
协作群中传播私钥。

## 启动命令

> 以下命令用于 Linux/托管服务器，不是当前 Windows 开发机的环境路径。
> 当前开发机统一使用 `docs/environment.md` 中的 D 盘 Python 与 uv 目录。

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

无外部密钥的故障诊断配置（不作为比赛产品模式）：

```dotenv
LLM_ENABLED=false
LIVE_ROUTE_ENABLED=false
LIVE_WEATHER_ENABLED=false
```

公网实时版：

```dotenv
LLM_ENABLED=true
LLM_MODEL=qwen3.7-plus
LLM_FALLBACK_MODELS=qwen-plus-2025-07-28,glm-5
LLM_BASE_URL=<百炼 OpenAI 兼容地址>
LLM_API_KEY=<服务器密钥>
LLM_ENABLE_THINKING=false
LLM_RENDER_ENABLED=true
LLM_PLAN_RENDER_ENABLED=false
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

比赛公网版建议启用轻量测试登录。首页和健康检查保持可访问，规划、地图、
天气、课表与记忆接口需要使用测试账号登录；登录后获得短期签名凭证。测试
账号、密码、签名密钥只能配置在部署环境变量中，不得写入 GitHub、前端或
PPT 源文件。参赛材料填写独立测试账号与有效期，不得提供管理员账号。

```text
APP_ACCESS_ENABLED=true
APP_TEST_USERNAME=yicheng_test
APP_TEST_PASSWORD=<单独生成的比赛测试密码>
APP_AUTH_SECRET=<至少24字符的随机签名密钥>
APP_ACCESS_HOURS=8
```

## 高德配额与公网 IP

- 确认高德账户完成个人开发者认证；
- 比赛版本不要购买额外流量包；
- 路线请求已按个人账户每秒 3 次限制进行节流；
- 地点坐标和七组核心路线已本地固化；
- 天气与路线失败时会自动降级；
- 服务器具有固定出口 IP 后，可以把该 IP 加入高德 Key 白名单；
- 若托管平台出口 IP 不固定，暂不配置 IP 白名单，但必须保管好 Key。

## 发布分支与协作

生产只跟踪 `main`。协作者使用 `feat/*`、`fix/*` 或 `docs/*` 分支，通过
Pull Request 合并；不要直接向 `main` 推送未验收代码。合并后由维护者执行
部署命令，再检查首页、健康接口、登录和固定 Demo。

密钥、`.env`、`runtime/*.db` 和服务器私钥不得进入 Git。GitHub 仓库协作者
在 `Settings → Collaborators` 管理；ECS Deploy key 只授予仓库只读拉取权限。

不能把纯静态网页托管当作完整部署，因为模型、SQLite、RAG、地图和天气均
运行在服务端。

## 发布流程

1. 冻结需求，不在发布当天新增功能；
2. 运行静态数据校验；
3. 运行全部 296 项自动化测试；
4. 运行 112 例综合评估和 24 场景规划算法基准；
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
