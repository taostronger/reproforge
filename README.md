# ReproForge — Bug 复现与回归智能体

> **大模型负责理解 Bug，Playwright 负责证明 Bug。**

测试人员边操作网页边口述 Bug（可选上传截图），ReproForge 自动采集证据、**复现 Bug**、求**最小复现**、生成可运行的 Playwright 回归测试、**检索历史相似 Bug**、定位可疑代码，最终输出一份可交付的 Bug 复现包（含 Markdown Issue）。

## 为什么做这个

- **素材全自造**：被测应用是预埋 Bug 的 React 商城 + Playwright 录屏，零真人/真实数据依赖，演示稳定可复现。
- **确定性底座**：浏览器操作走 Playwright 真实回放，不靠"从视频玄学猜操作"——Bug 是否复现是**跑出来的**，不是猜出来的。
- **真·多模态**：语音（whisper 口述）+ 操作（Playwright）+ **视觉（VL 看 Bug 截图）**+ 文本（LLM）四路融合，对齐赛题"多模态 Agent"。
- **会记忆**：历史 Bug 入向量库（RAG），复现新 Bug 时检索相似案例辅助定位，越用越聪明。
- **多智能体协作**：6 个节点（vision / evidence / reproduction / recall / investigator / regression）由 LangGraph 编排，对齐 NVIDIA AI-Q Blueprint 的 "Intent → 子代理 → Sandbox+Tools" 形态。

## 工作流程

```
截图(可选) + 操作 + 口述
   │
   ▼
[vision]          VL 看截图提 expected/actual（step-3.7 多模态；无图则跳过）
   │
   ▼
[evidence]        构建 Bug 时间线，综合口述 + 视觉提 expected/actual
   │
   ▼
[reproduction]    生成 Playwright 测试 → 连跑 3 次判稳定 → 修定位器(≤2轮) → 最小复现
   │
   ▼
[recall]          RAG 检索历史相似 Bug（chromadb + bge；空库则跳过）
   │
   ▼
[investigator]    ripgrep + tree-sitter 检索候选 + 历史参考 → LLM 打分 → Top3 可疑文件
   │
   ▼
[regression]      审核断言/选择器 + 生成 Markdown Issue → 入记忆库
```

**核心创新——最小复现**：拿到能稳定复现 Bug 的测试后，逐个尝试删除"候选可删步骤"（浏览/无关点击），删后重跑——Bug 仍在则永久删除，求出**最短稳定复现路径**。

**多模态 + 记忆都是可选 + 降级**：不上传截图 / `REPROFORGE_VL=off` → vision 跳过；无记忆库 / `REPROFORGE_MEMORY=off` → recall 跳过。任一缺失，主流水线照跑（核心 4 节点不变）。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（StateGraph 串联 6 节点） |
| LLM | Stepfun step-3.7-flash（开发期远程，**原生多模态支持图像**）/ qwen3.6-35b（Demo 本地 vLLM，双轨切换） |
| 视觉（VL） | step-3.7-flash 多模态看 Bug 截图提 expected/actual |
| 记忆（RAG） | chromadb 持久化 + bge-large-zh embedding |
| 浏览器 | Playwright（录制 + 生成回归测试 + 真实回放判通过/失败） |
| ASR | faster-whisper（带时间戳中文转写，CPU + int8） |
| 检索 | ripgrep + tree-sitter（提取命中所在函数/组件作上下文） |
| UI | Gradio |
| 平台 | NVIDIA DGX Spark（GB10 Grace Blackwell，本地部署） |

## 项目结构

```
reproforge_spike/
├── agents/          # 6 节点：vision / evidence / reproduction / recall / code_investigator / regression
├── graph/           # LangGraph 编排（StateGraph）
├── memory/          # RAG 记忆库（chromadb + bge-large-zh）
├── test_runner/     # Playwright 测试运行器（--reporter=json + 连跑判稳定）
├── code_search/     # ripgrep + tree-sitter 检索（双模式降级）
├── minimization/    # 最小复现算法（核心创新）
├── llm/             # OpenAI 兼容模型抽象（双轨 + 多模态 chat_vision）
├── capture/ asr/    # Playwright 录制 / faster-whisper 转写
├── ui/              # Gradio 界面（操作 + 口述 + 截图 → Issue）
├── eval/            # 评测指标（复现率/最小化率/定位轮数 + 远程vs本地对比）
├── demo_project/    # 被测 React+Vite 商城（预埋 3 个 Bug）
├── spike/           # 冒烟脚本（smoke_phase3 / smoke_vl / smoke_rag）
└── tests/           # pytest（全 mock 单测 + 真调冒烟）
```

## 快速开始

```bash
# 1. Python 依赖（建议清华镜像）
pip install langgraph openai pydantic python-dotenv faster-whisper \
            tree-sitter tree-sitter-typescript gradio pytest
pip install chromadb sentence-transformers          # RAG 记忆库
pip install playwright && playwright install chromium

# 2. 配 Stepfun key
echo 'STEPCONFIG_FUN_API_KEY=你的key' > .env

# 3. 起被测应用
cd demo_project && npm install && npm run dev   # http://localhost:5173

# 4. 端到端冒烟
python spike/smoke_phase3.py      # 复现 Bug1（远程 step-3.7）
python spike/smoke_vl.py          # VL：验证 step-3.7 图像能力
python spike/smoke_rag.py         # RAG：验证 bge + chromadb（需 torch>=2.4）

# 5. 起 Gradio UI（可上传 Bug 截图触发 VL）
python -m ui.app   # http://localhost:7860
```

## 双轨模型（开发 ↔ Demo 零代码切换）

`config.py` 用环境变量 `PROFILE` 切换：

- 默认 → Stepfun 远程 API（开发期，迭代快、不占本地显存）
- `PROFILE=local` → 本地模型 on DGX Spark（Demo / 评审期，满足"本地算力部署"要求）

业务代码零改动，只换 `base_url` + `model`。VL 同样双轨：预赛远程 step-3.7 多模态，决赛补本地 Qwen2.5-VL。

## 本地部署（DGX Spark）

> 完整启动命令、显存实测、踩坑记录见 `docs/架构与部署.md`。

spark-71（GB10，128GB 统一内存）上 vLLM 托管 qwen3.6-35b（fp8）。**关键坑：必须 `-e VLLM_USE_DEEP_GEMM=0`**（nightly vLLM 的 DeepGEMM 在 GB10 上 NVCC JIT 会失败）。util 0.8 实测占 ~100GB / 119GB。

```bash
# spark-71 上起 vLLM（带 DeepGEMM=0）
docker run -d --name vllm --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models eugr/spark-vllm:latest \
  vllm serve /models/qwen36-35b-a3b --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 --gpu-memory-utilization 0.8 --max-model-len 8192 \
  --load-format fastsafetensors --kv-cache-dtype fp8 --enable-prefix-caching

# 本地建隧道 + 切本地模型（必须覆盖 LOCAL_BASE_URL / LOCAL_MODEL）
ssh -L 8000:localhost:8000 -p 6071 Developer@106.13.186.155
PROFILE=local LOCAL_BASE_URL=http://localhost:8000/v1 \
  LOCAL_MODEL=/models/qwen36-35b-a3b python spike/smoke_phase3.py
```

## 评测

`eval/metrics.py` 在多个 Bug 上跑全流程，汇总：复现成功率 / 测试生成成功率 / 最小化率 / 定位器修复轮数。`eval/compare.py` 对比远程(Stepfun) vs 本地(qwen3.6)。

## 设计亮点

- **多模态（VL）+ 记忆（RAG）全程降级**：vision / recall 任一缺失或失败 → 跳过，主流水线照跑。移除两节点后等同原版 4-agent 流水线。
- **降级链贯穿全程**：evidence 低置信度 → 人工确认；reproduction 不稳定 → 2 轮定位器上限；code_search 无 ripgrep → 纯 Python 遍历；regression LLM 不可用 → 确定性 fallback Issue。
- **冒烟驱动**：mock 测试漏掉的真实 bug（代码围栏 / 漏 import / 路径正则 / 编码 / 测试产物污染）均由真调端到端冒烟发现并修复。

## 团队分工与贡献

**taostronger 队**（2 人，实际产能 = 1 名开发者，MVP 按单人可完成设计、每个功能配降级兜底）

| 成员 | 角色 | 贡献 |
|---|---|---|
| tz（队长） | 主力开发 | 整体架构；6 节点 Agent（vision / evidence / reproduction / recall / investigator / regression）；LangGraph 编排；**最小复现算法**（核心创新）；**VL 视觉**（step-3.7 多模态看截图）；**RAG 记忆**（chromadb + bge-large-zh）；Playwright 运行器；ripgrep + tree-sitter；双轨模型层；DGX Spark vLLM 部署；pytest 用例与冒烟；README 与文档 |
| liwenY（队员） | 非技术辅助 | 被测商城 Bug 场景与素材设计；Demo 视频录制与剪辑；界面审美把控；路演材料与现场协助 |

## 未来展望

- **本地 VL**：远程 step-3.7 多模态 → 决赛补本地 Qwen2.5-VL（vLLM 第二实例）
- **自动截图**：接 capture trace / reproduction 失败截图，去掉手动上传
- **RAG 增强**：重排 / 混合检索 / 记忆库去重过期
- **CI 集成**：生成的回归测试接入 GitHub Actions
- **最小复现增强**：代码覆盖率指导删步

---

*NVIDIA DGX Spark 多模态 Agent 黑客松 · 2026*
