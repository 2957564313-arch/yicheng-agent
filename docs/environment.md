# 开发环境

## 固定环境

- Python 3.12
- uv
- SQLite
- FastAPI
- LangGraph
- pytest

Docker、Conda 和 Node 构建链不是本项目本地开发前置。

## 当前机器基线

- 系统 Python：3.14.2，不用于本项目
- Codex 内置 Python：3.12.13，仅用于引导安装本地 uv
- Git：2.50.1
- SQLite CLI：3.51.0
- uv：团队成员自行安装，不把安装程序放入项目目录

当前工作区的 Python 3.12 虚拟环境和依赖已经配置完成，可直接使用下面的
“复现”命令。团队其他电脑仍需先安装 uv，再执行 `uv sync`。

外部能力当前也已完成本地联调：

- 千问：`qwen3.7-plus`；
- 高德：地点搜索、步行路线和天气；
- 校园知识：学生手册与结构化时间规则；
- `.env`：本机已配置，禁止复制到提交材料或 Git。

## 复现

```powershell
$env:UV_CACHE_DIR = 'D:\APP\Dev\Python\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = 'D:\APP\Dev\Python\envs\yicheng-agent'
uv sync
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe --version
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe -m pytest
```

完成一次 `uv sync` 后，统一直接使用
`D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe`；项目目录和
C 盘均不创建 `.venv`。

## 从零配置

1. 安装 Git 与 uv。
2. 进入项目目录，设置
   `UV_CACHE_DIR=D:\APP\Dev\Python\uv-cache` 和
   `UV_PROJECT_ENVIRONMENT=D:\APP\Dev\Python\envs\yicheng-agent`，
   再执行 `uv sync`。
3. 复制 `.env.example` 为 `.env`。先验证确定性核心和冻结 Demo，
   再填写模型与高德 Key，正式交互使用联网的 `auto` 模式；
4. 执行
   `& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe -m scripts.init_db`。
5. 执行
   `& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe -m pytest`。
6. 执行
   `& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe -m uvicorn app.main:app --reload`。
7. 打开 <http://127.0.0.1:8000/>，依次运行三个演示按钮。

## 当前推荐模型参数

```dotenv
LLM_ENABLED=true
LLM_MODEL=qwen3.7-plus
LLM_FALLBACK_MODELS=qwen-plus-2025-07-28,glm-5
LLM_ENABLE_THINKING=false
LLM_RENDER_ENABLED=true
LLM_PLAN_RENDER_ENABLED=false
LLM_TIMEOUT_SECONDS=10
```

关闭深度思考是必要配置。规划节点需要快速、稳定的 JSON，而不是长推理
文本。系统按主模型、备用模型顺序调用；额度耗尽、限流、暂时不可用或响应
结构异常时自动换下一个模型。全部在线模型不可用时，仍由确定性约束层和
排程器继续完成核心功能。比赛版默认不对已校验计划进行第二次模型润色，
避免模型改动时间事实并降低端到端响应时间；知识问答仍可使用模型组织语言。

## 外部能力启用与验收顺序

必须按以下顺序启用，禁止一次性同时打开三个外部依赖：

1. 导入并核验校园知识库；
2. 配置一个 OpenAI 兼容模型；
3. 补齐真实地点坐标后配置路线服务；
4. 最后配置天气服务。

每启用一项都要重新运行自动化测试和三个 Demo。任何一项失败时，
系统应回退到对应的确定性数据源，不能阻断核心排程；正常请求始终按联网
优先链路执行。

真实接口验收：

```powershell
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe scripts\probe_qwen_model.py --model qwen3.7-plus
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe scripts\live_amap_smoke.py
& D:\APP\Dev\Python\envs\yicheng-agent\Scripts\python.exe scripts\live_end_to_end_smoke.py
```

上述脚本只输出模型名、状态、路线、天气和错误类型，不打印 Key。
