# ReproForge — Bug 复现与回归智能体

> **大模型理解 Bug，Playwright 证明 Bug。**

测试员边操作边口述（可选上传截图 / 视频 / 录音），ReproForge 自动采集证据、**复现 Bug**、求**最小复现**、生成可运行的 Playwright 回归测试、**检索历史相似 Bug**、定位可疑代码，最终输出一份可交付的 Bug 复现包（含 Markdown Issue）。

## 特性

- **6 节点流水线**（LangGraph）：`vision → evidence → reproduction → recall → investigator → regression`
- **多输入**：🖱️ 录制网页操作 / 🎬 上传视频 / 🎤 语音口述 / 手填 JSON + 截图
- **真·多模态**：语音(whisper) + 操作(Playwright) + **视觉(VL 看截图)** + 文本(LLM)
- **会记忆**：历史 Bug 入向量库（RAG），新 Bug 检索相似案例辅助定位
- **双轨模型**：开发远程 step-3.7 / Demo 本地 vLLM（qwen3.6）
- **商城 ↔ 工具跳转**：商城 🐞 Report Bug → ReproForge；ReproForge → 商城
- **全降级**：VL / RAG / 录制 / 视频 任一失败 → 主流水线照跑

## 工作流程

```
截图/视频/语音(可选) + 操作 + 口述
   │
   ▼
[vision]      VL 看截图提 expected/actual（step-3.7 多模态；无图则跳过）
   ▼
[evidence]    综合 口述+视觉 提 expected/actual
   ▼
[reproduction] 生成 Playwright 测试 → 连跑 3 次判稳定 → 最小复现
   ▼
[recall]      RAG 检索历史相似 Bug（chromadb+bge；空库则跳过）
   ▼
[investigator] ripgrep+tree-sitter + 历史参考 → LLM 打分 → Top3 可疑文件
   ▼
[regression]  审核 + 生成 Markdown Issue → 入记忆库
```

**核心创新——最小复现**：逐个尝试删除"候选可删步骤"，删后重跑，Bug 仍在则永久删除，求出**最短稳定复现路径**。

## 技术栈

| 层 | 选型 |
|---|---|
| 编排 | LangGraph（StateGraph 串联 6 节点）|
| LLM | step-3.7-flash（远程）/ qwen3.6-35b（本地 vLLM，双轨）|
| VL 视觉 | step-3.7 多模态（本地 Qwen2.5-VL 待决赛）|
| RAG 记忆 | chromadb + bge-large-zh（bge 待挪 spark-71）|
| 操作采集 | Playwright（录制 + reproduction 真实回放）|
| 视频输入 | imageio-ffmpeg 提音频 + whisper ASR + opencv 抽帧 + LLM 提操作 |
| ASR | faster-whisper（CPU int8）|
| 检索 | ripgrep + tree-sitter |
| UI | Gradio（步骤式）|
| 平台 | NVIDIA DGX Spark（GB10，本地部署）|

## 项目结构

```
reproforge_spike/
├── agents/          # 6 节点：vision/evidence/reproduction/recall/code_investigator/regression
├── graph/           # LangGraph 编排
├── memory/          # RAG 记忆库（chromadb + bge-large-zh）
├── capture/         # recorder（录制操作）+ video_parser（视频→actions/口述/截图）
├── test_runner/     # Playwright 测试运行器（连跑判稳定）
├── code_search/     # ripgrep + tree-sitter 检索
├── minimization/    # 最小复现算法（核心创新）
├── llm/             # OpenAI 兼容抽象（双轨 + 多模态 chat_vision + thinking 剥标签）
├── asr/             # faster-whisper
├── ui/              # Gradio 步骤式界面
├── eval/            # 评测指标 + 远程vs本地对比
├── demo_project/    # 被测 React+Vite 商城（预埋 Bug）
├── spike/           # 冒烟脚本
└── tests/           # pytest（全 mock）
```

## 快速开始

```bash
# 依赖（清华镜像）
pip install langgraph openai pydantic python-dotenv faster-whisper \
            tree-sitter tree-sitter-typescript gradio pytest \
            chromadb sentence-transformers opencv-python imageio-ffmpeg
pip install playwright && playwright install chromium

echo 'STEPCONFIG_FUN_API_KEY=你的key' > .env
cd demo_project && npm install && npm run dev   # :5173
python -m ui.app                                # :7860
```

## 本地部署（DGX Spark）

> 详见 `docs/架构与部署.md`。

spark-71 上 vLLM 托管 qwen3.6-35b（fp8）。**关键坑：必须 `-e VLLM_USE_DEEP_GEMM=0`**（nightly DeepGEMM 在 GB10 上 NVCC JIT 失败）。util 0.8 实测占 ~100GB/119GB。

```bash
docker run -d --name vllm --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models eugr/spark-vllm:latest \
  vllm serve /models/qwen36-35b-a3b --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size 1 --gpu-memory-utilization 0.8 --max-model-len 8192 \
  --load-format fastsafetensors --kv-cache-dtype fp8 --enable-prefix-caching
```

## 未来展望

- **bge embedding 挪 spark-71**：当前 bge 本地（设计缺陷，用户机不该装 torch）。决赛：spark-71 起 bge 服务，本地 chromadb 调远程。
- **VL 模型（Qwen2.5-VL）spark-71**：当前 VL 远程 step-3.7。决赛：spark-71 vLLM 第二实例，双轨 VL。
- **自动截图**：接 capture/reproduction 失败截图，去掉手动上传。
- **CI 集成**：生成的回归测试接入 GitHub Actions。

## 团队

**taostronger 队**（2 人，实际产能 1 开发者，MVP 按单人设计、每功能配降级）

| 成员 | 贡献 |
|---|---|
| tz（队长）| 架构；6 节点 Agent；最小复现算法；VL 视觉；RAG 记忆；操作采集（Playwright）；视频输入；双轨模型；vLLM 部署；测试+冒烟；文档 |
| liwenY（队员）| 商城 Bug 场景与素材；Demo 视频录制剪辑；审美；路演 |

---

*NVIDIA DGX Spark 多模态 Agent 黑客松 · 2026*
