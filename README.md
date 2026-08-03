# 易程智策

面向大学生的日程规划助手：用一句话描述课程、学习、出行、取件或运动，系统会给出可执行的时间安排，并支持课表、提醒和个人偏好。

## 当前情况

- 公网地址：<https://yichengapp.top/>
- 健康检查：<https://yichengapp.top/api/v1/health>
- 生产环境：阿里云 ECS + Cloudflare + FastAPI + SQLite
- 生产代码：GitHub `main` 分支
- 旧 Vercel 地址：不再使用
- 本地开发目录：`D:\APP\Dev\repos\yicheng-agent`

## 本地运行

需要 Python 3.12、`uv`。在项目目录执行：

```powershell
$env:UV_CACHE_DIR = 'D:\APP\Dev\Python\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = 'D:\APP\Dev\Python\envs\yicheng-agent'
uv sync
uv run python -m scripts.init_db
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后打开 <http://127.0.0.1:8000/>。

也可以直接运行项目根目录的 `启动易程智策.command`。

## 协作开发

仓库：<https://github.com/2957564313-arch/yicheng-agent>

1. 从最新 `main` 创建分支，例如 `feat/chat-ui`、`fix/login`、`docs/readme`。
2. 在自己的分支修改并运行 `uv run pytest -q`。
3. 推送分支，提交 Pull Request，写清改了什么和如何验证。
4. 审查通过后合并到 `main`。
5. 合并后再发布到公网。

协作者由仓库管理员在 GitHub 的 `Settings → Collaborators` 添加。不要提交 `.env`、数据库、API Key、测试密码或 SSH 私钥。

## 发布公网

确认 PR 已合并到 `main` 后，在 PowerShell 执行：

```powershell
ssh -i 'D:\key\yicheng-ecs-2026.pem' `
  ecs-user@120.26.65.5 "sudo /usr/local/sbin/yicheng-deploy"
```

发布后检查：

```text
https://yichengapp.top/
https://yichengapp.top/api/v1/health
```

服务器上的部署脚本会拉取最新 `main`，保留生产 `.env` 和 `runtime/` 数据。

## 常用检查

```powershell
uv run pytest -q
uv run python scripts/validate_static_data.py
```

接口文档：<http://127.0.0.1:8000/docs>

更多部署细节见 [`docs/deployment.md`](docs/deployment.md)，演示流程见 [`docs/demo_script.md`](docs/demo_script.md)。
