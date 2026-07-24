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

```bash
uv sync
uv run python --version
uv run python -m pytest
```

完成一次 `uv sync` 后，也可以直接使用 `.venv/bin/python` 和
`.venv/bin/pytest`，不依赖项目内的临时安装目录。

## 从零配置

1. 安装 Git 与 uv。
2. 进入项目目录，执行 `uv sync`。
3. 复制 `.env.example` 为 `.env`。先保持外部能力为 `false`，验证
   离线 Demo，再在本机填写自己的 Key；
4. 执行 `uv run python -m scripts.init_db`。
5. 执行 `uv run python -m pytest`。
6. 执行 `uv run uvicorn app.main:app --reload`。
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
结构异常时自动换下一个模型。全部在线模型不可用时，仍由本地规则和确定性
排程继续完成核心功能。比赛版默认不对已校验计划进行第二次模型润色，
避免模型改动时间事实并降低端到端响应时间；知识问答仍可使用模型组织语言。

## 外部能力启用与验收顺序

必须按以下顺序启用，禁止一次性同时打开三个外部依赖：

1. 导入并核验校园知识库；
2. 配置一个 OpenAI 兼容模型；
3. 补齐真实地点坐标后配置路线服务；
4. 最后配置天气服务。

每启用一项都要重新运行自动化测试和三个 Demo。任何一项失败时，
系统应回退到离线模式，不能阻断核心排程。

真实接口验收：

```bash
.venv/bin/python scripts/probe_qwen_model.py --model qwen3.7-plus
.venv/bin/python scripts/live_amap_smoke.py
.venv/bin/python scripts/live_end_to_end_smoke.py
```

上述脚本只输出模型名、状态、路线、天气和错误类型，不打印 Key。
