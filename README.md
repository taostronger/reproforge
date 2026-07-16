# ReproForge — Bug 复现与回归智能体

> **大模型负责理解 Bug，Playwright 负责证明 Bug。**

测试人员边操作网页边口述 Bug，ReproForge 自动采集证据、**复现 Bug**、求**最小复现**、生成可运行的 Playwright 回归测试、定位可疑代码，最终输出一份可交付的 Bug 复现包（含 Markdown Issue）。

## 为什么做这个

- **素材全自造**：被测应用是预埋 Bug 的 React 商城 + Playwright 录屏，零真人/真实数据依赖，演示稳定可复现。
- **确定性底座**：浏览器操作走 Playwright 真实回放，不靠"从视频玄学猜操作"——Bug 是否复现是**跑出来的**，不是猜出来的。
- **多智能体协作**：4 个 LLM Agent 分工（证据分析 / 复现工程 / 代码调查 / 回归审查），由 LangGraph 编排，对齐 NVIDIA AI-Q Blueprint 的 "Intent → 子代理 → Sandbox+Tools" 形态。

## 工作流程

```
操作 + 口述
   │
   ▼
[evidence]        构建 Bug 时间线，从口述提取 expected / actual
   │
   ▼
[reproduction]    生成 Playwright 测试 → 连跑 3 次判稳定 → 修定位器(≤2轮) → 最小复现
   │
   ▼
[code_investigator] ripgrep + tree-sitter 检索候选 → LLM 打分排序 → Top3 可疑文件
   │
   ▼
[regression]      审核断言/选择器 + 生成 Markdown Issue（预期/实际/最小复现步骤/稳定率/可疑代码）
```

**核心创新——最小复现**：拿到能稳定复现 Bug 的测试后，逐个尝试删除"候选可删步骤"（浏览/无关点击），删后重跑——Bug 仍在则永久删除，求出**最短稳定复现路径**。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（StateGraph 串联 4 agent） |
| 模型 | Stepfun step-3.7-flash（开发期远程）/ qwen3.6-35b（Demo 本地，双轨切换） |
| 浏览器 | Playwright（录制 + 生成回归测试 + 真实回放判通过/失败） |
| ASR | faster-whisper（带时间戳中文转写） |
| 检索 | ripgrep + tree-sitter（提取命中所在函数/组件作上下文） |
| UI | Gradio |
| 平台 | NVIDIA DGX Spark（GB10 Grace Blackwell，本地部署） |

## 项目结构

```
reproforge_spike/
├── agents/          # 4 个 LLM Agent：evidence / reproduction / code_investigator / regression
├── graph/           # LangGraph 编排（StateGraph）
├── test_runner/     # Playwright 测试运行器（--reporter=json + 连跑判稳定）
├── code_search/     # ripgrep + tree-sitter 检索（双模式降级）
├── minimization/    # 最小复现算法（核心创新）
├── llm/             # OpenAI 兼容模型抽象（双轨切换层）
├── capture/ asr/    # Playwright 录制 / faster-whisper 转写
├── ui/              # Gradio 界面
├── eval/            # 评测指标（复现率/最小化率/定位轮数）
├── demo_project/    # 被测 React+Vite 商城（预埋 3 个 Bug）
├── spike/           # 冒烟脚本（端到端验证）
└── tests/           # pytest（41 过 / 2 skip）
```

## 快速开始

```bash
# 1. Python 依赖（gradio 默认源易超时，建议清华镜像）
pip install langgraph openai pydantic python-dotenv faster-whisper \
            tree-sitter tree-sitter-typescript gradio pytest
pip install playwright && playwright install chromium

# 2. 配 Stepfun key
echo 'STEPCONFIG_FUN_API_KEY=你的key' > .env

# 3. 起被测应用
cd demo_project && npm install && npm run dev   # http://localhost:5173

# 4. 端到端冒烟（复现 Bug1：总价不随数量更新）
python spike/smoke_phase3.py

# 5. 起 Gradio UI
python -m ui.app   # http://localhost:7860
```

## 双轨模型（开发 ↔ Demo 零代码切换）

`config.py` 用环境变量 `PROFILE` 切换：

- 默认 → Stepfun 远程 API（开发期，迭代快、不占本地显存）
- `PROFILE=local` → 本地模型 on DGX Spark（Demo / 评审期，满足"本地算力部署"要求）

业务代码零改动，只换 `base_url` + `model`（Stepfun 与本地 vLLM/llama-server 都是 OpenAI 兼容）。

## 评测

`eval/metrics.py` 在多个 Bug 上跑全流程，汇总：复现成功率 / 测试生成成功率 / 最小化率 / 定位器修复轮数。

## 设计亮点

- **降级链贯穿全程**：evidence 低置信度 → 需人工确认；reproduction 不稳定 → 2 轮定位器修复上限；code_search 无 ripgrep → 纯 Python 遍历；regression LLM 不可用 → 确定性 fallback Issue。
- **冒烟驱动**：4 个 mock 测试漏掉的真实 bug（代码围栏 / 漏 import / 路径正则 / 编码 / 测试产物污染）均由真调端到端冒烟发现并修复。

## 团队

**taostronger 团队**：开发（架构 / 编码 / 测试）+ 非编码成员（素材录制 / 审美把控 / 视频 / 路演）

---

*NVIDIA DGX Spark 多模态 Agent 黑客松 · 2026*
