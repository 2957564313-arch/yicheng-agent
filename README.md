# 易程智策

面向大学生的校园日程助手。输入课程、学习、出行、取件或运动安排后，系统会整理成可执行的计划，并支持课表、提醒、偏好和日/周/月日程查看。

## 当前线上版本

- 网站：https://yichengapp.top/
- 健康检查：https://yichengapp.top/api/v1/health
- 代码仓库：https://github.com/2957564313-arch/yicheng-agent（`main`）
- 生产环境：阿里云 ECS + Cloudflare Tunnel
- 主工作区：`D:\APP\Dev\repos\yicheng-agent`
- Vercel：已停用

## 当前使用的技术

- 后端：Python 3.12、FastAPI、Uvicorn
- 数据：SQLite、JSON 校园数据、SQLite-Vec 本地检索
- 前端：HTML、CSS、原生 JavaScript，无前端框架依赖
- 在线服务：阿里云大模型接口、高德地图路线和天气接口
- 登录：易程智策自有账号；手机和电脑登录同一账号后自动读取同一份云端数据
- 测试：比赛测试账号进入独立空间，不连接任何个人杭助数据
- 杭助：登录后由每位用户绑定自己的个人访问令牌，令牌加密保存且不会显示或导出
- 校园数据：杭助同步课程、考试、图书馆自习预约和二课安排，取消后下次同步自动移除
- 可靠性：在线接口失败时使用确定性规划和本地数据兜底
- 页面：对话、日/周/月日程、杭电助手、课程与校历和偏好均为独立入口
- 对话：历史记录保存在服务端，可修改旧提问并保留为新分支

## 本地运行（D 盘）

```powershell
cd D:\APP\Dev\repos\yicheng-agent
$env:UV_CACHE_DIR = 'D:\APP\Dev\Python\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = 'D:\APP\Dev\Python\envs\yicheng-agent'
uv sync
uv run python -m scripts.init_db
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/。

## 协作流程

1. 从 `main` 创建功能分支，例如 `feat/schedule-view`。
2. 修改后运行 `uv run pytest -q`。
3. 推送分支并提交 Pull Request。
4. 审查通过后合并到 `main`，再发布公网。

不要提交 `.env`、数据库、API Key、测试密码或 SSH 私钥。协作者在 GitHub 仓库的 Settings → Collaborators 中添加。

## 发布与检查

服务器已配置 GitHub deploy key。合并到 `main` 后，在 PowerShell 执行：

```powershell
ssh -i 'D:\key\yicheng-ecs-2026.pem' `
  ecs-user@120.26.65.5 "sudo /usr/local/sbin/yicheng-deploy"
```

发布后检查网站和 `/api/v1/health`。完整测试：

```powershell
uv run pytest -q
uv run python scripts/validate_static_data.py
```

天气接口只提供当前及近期预报；历史演示日期使用 `data/weather_fallback.json` 中的明确演示数据，并会标记为演示来源，不冒充实时天气。
