# ReproForge — 多模态 Bug 复现与回归智能体

> **大模型理解 Bug，Playwright 证明 Bug。**
> NVIDIA DGX Spark 多模态 Agent 黑客松 · **taostronger 队** · 2026

**项目报告书**

测试员边操作边口述（可选上传截图 / 视频 / 录音），ReproForge 自动采集证据、**复现 Bug**、求**最小复现**、生成可运行的 Playwright 回归测试、**检索历史相似 Bug**、定位可疑代码，最终输出一份可交付的 Bug 复现包（含 Markdown Issue）。

---

## 一、项目概述

### 1.1 名称
**ReproForge** —— Reproduction（复现）+ Forge（锻造）：把模糊的「Bug 口述」锻造为可复现、可回归、可记忆的工程产物。

### 1.2 目标
构建一个多模态 Bug 复现与回归智能体：输入「截图 / 视频 / 语音 + 操作 + 口述」，输出
1. 可运行的 Playwright 回归测试（带断言、连跑稳定）；
2. 最小复现路径（稳定 1-minimal 复现序列）；
3. 可交付的 Markdown Bug Issue；
4. （可选）历史相似 Bug 参考与可疑代码排序。

### 1.3 背景
Web 应用测试中，Bug 复现高频却低效：
- **复现成本高**：手工写回归、反复试错定位最小路径，耗时依赖经验；
- **口述难落地**：测试员能口述意图，却难直接转为可运行产物；
- **经验不沉淀**：相似 Bug 反复出现，无法参考历史；
- **多模态信息浪费**：截图、录屏、语音里的线索被传统流程丢弃。

ReproForge 用**大模型理解 Bug**（多模态提意图）+ **Playwright 证明 Bug**（真实回放判稳定）+ **RAG 沉淀经验**，把测试员的隐性知识转化为团队可复用的资产。

---

## 二、作品介绍（功能与亮点）

### 2.1 六节点流水线（LangGraph）

```
截图/视频/语音(可选) + 操作 + 口述
   │
   ▼
[vision]        VL 看截图提 expected/actual（本地 Qwen2.5-VL；无图则跳过）
   ▼
[evidence]      综合 口述 + 视觉 提 expected/actual（低置信→人工确认）
   ▼
[reproduction]  生成 Playwright 测试 → 连跑 3 次判稳定 → 最小复现
   ▼
[recall]        RAG 检索历史相似 Bug（chromadb + bge；空库则跳过）
   ▼
[investigator]  ripgrep + tree-sitter + 历史参考 → LLM 打分 → Top3 可疑文件
   ▼
[regression]    审核 + 生成 Markdown Issue → 入记忆库
```

### 2.2 多模态输入
🖱️ 录制网页操作 / 🎬 上传视频 / 🎤 语音口述 / ✍️ 手填 JSON + 截图 —— 覆盖测试员的全部表达方式。

### 2.3 产品亮点
- **真·多模态**：语音（whisper）+ 操作（Playwright）+ 视觉（VL 看截图）+ 文本（LLM）四位一体；
- **会记忆**：历史 Bug 入向量库，新 Bug 检索相似案例辅助定位；
- **本地为主 + 远程加固**：三服务全本地（DGX Spark），远程 Stepfun 作 fallback；
- **优雅降级**：VL / RAG / 录制 / 视频 / 任一服务挂掉 → 核心复现链路照跑，并明确标记缺失证据与能力降级（不宣称零退化）；
- **商城 ↔ 工具跳转**：商城 🐞 Report Bug → ReproForge，闭环演示。

---

## 三、技术创新点

### 3.1 最小复现算法（核心创新，确定性）
拿到能稳定复现的测试后，求**稳定 1-minimal 复现路径**（任一剩余步骤都无法再单独删除，不保证全局最短）：逐个尝试删除「候选可删步骤」（click/hover 类无关步骤，保留关键填写），删后用子集重新生成 spec **真跑**，Bug 仍在则永久删除，否则保留，重复直到无可删。

> **纯确定性算法，不依赖 LLM 猜**。开发者拿到最小步骤，照着点几下就能复现，不用在十几步无关操作里找。

### 3.2 本地为主 + 远程 fallback（服务加固）
模型调用层做成「本地优先 + 远程兜底」的双客户端：文本 / VL 本地 vLLM 优先，仅对**服务不可用类异常**（连接 / 超时 / 5xx）降级远程 Stepfun，4xx / 鉴权不降级。业务代码零感知，演示稳定性大幅提升。

### 3.3 多模态融合的证据提取
`evidence` 节点按置信度合并「口述提取」与「VL 视觉提取」：高置信优先，冲突时 `needs_confirm` 转人工，vision 未用则完全走口述（现有逻辑零改动）。多模态不是堆叠，而是可降级的协同。

### 3.4 RAG 记忆（经验沉淀）
历史 Bug 入 chromadb（文档 = 预期 + 实际 + 可疑文件 + testid），新 Bug 检索 Top-3 相似历史注入 `investigator` 的打分 prompt 作线索（仅作线索，不视为结论）。冷启动（空库）等同无记忆，自然过渡。

### 3.5 全降级链（生产级健壮性）
每个节点都「可选输入 + try/except 全包 + 失败返回空」：evidence 低置信→人工确认；reproduction 不稳定→2 轮定位器上限；code_search 无 ripgrep→纯 Python 遍历；regression LLM 挂→确定性 Issue。移除 vision/recall 节点流水线仍跑通。

### 3.6 对齐 NVIDIA Agent Toolkit 三层
架构正对齐 NVIDIA 官方「System of Models → Harness → Secure Runtime + Skills」框架（与官方 AI-Q 深度研究 Blueprint 同用 LangGraph），路演即get。

---

## 四、NVIDIA SDK / 模型使用说明

### 4.1 平台：NVIDIA DGX Spark（GB10 Grace Blackwell）
- 配置：1× GB10（128GB LPDDR5x 统一内存，系统显示 ~119GiB）/ 20 核 / 3.7TB NVMe；
- 充分利用本地算力部署三服务，满足「本地算力部署」评审要求。

### 4.2 推理：vLLM（OpenAI 兼容，nightly v0.23.1rc1）
三服务同机共存，统一 OpenAI 兼容接口，业务代码经抽象层零改动切换：

| 服务 | 端口 | 模型 | util | 用途 |
|---|---|---|---|---|
| 文本 vLLM | :8000 | **qwen3.6-35b-a3b**（35B MoE fp8）| 0.45 | 文本 LLM 主力 |
| VL vLLM | :8001 | **Qwen2.5-VL-7B-Instruct** | 0.3 | 视觉看截图 |
| bge embedding | :8002 | **bge-large-zh-v1.5** | CPU | RAG 向量化 |

远程 **Stepfun step-3.7 / 多模态** 作 fallback（开发期主用 + 演示期兜底）。

### 4.3 关键优化（实测）
1. **`VLLM_USE_DEEP_GEMM=0`**：nightly DeepGEMM 在 GB10 NVCC JIT 编译失败，禁用走 Triton/FlashInfer；
2. **显存共存调优**：文本 0.45 + VL 0.4 会占满 119GB，VL 降到 0.3 后峰值 ~108GB、留 ~11GB；
3. **VL 多模态参数**：`--limit-mm-per-prompt '{"image":1}'`（JSON 格式）；
4. **模型分发**：Qwen 官方 modelscope 镜像下载（hf-mirror 大文件 Xet CAS 超时）；
5. **bge 服务化**：embedding 下沉 spark-71（FastAPI + sentence-transformers，CPU），演示机不再装 torch；
6. **fp8 + prefix caching**：文本实例 `--kv-cache-dtype fp8 --enable-prefix-caching` 降显存提吞吐。

### 4.4 编排：LangGraph（对齐官方 AI-Q Blueprint）
用 LangGraph StateGraph 线性串联 6 节点，与 NVIDIA 官方 AI-Q 深度研究 Blueprint（Intent Router → 子代理 → Sandbox + Tools）同形态。

### 4.5 其他 SDK / 技能
- **Playwright**：录制操作 + reproduction 真实回放（隔离执行环境，确定性证明 Bug）；
- **faster-whisper**（CPU int8）：ASR，不占 GPU；
- **ripgrep + tree-sitter**：代码检索 skill；
- **chromadb**：RAG 向量库。

---

## 五、系统架构与数据流

### 5.1 架构总览

```
截图(可选)  actions[]      segments[]        console[]
(VL视觉)   (Playwright     (faster-whisper    (browser
           录制操作)         语音转写)          console)
   │           │                  │                 │
   └────┬──────┴────────┬─────────┴─────────────────┘
        ▼               ▼
  ┌──────────────────────────────────────────────┐
  │      LangGraph StateGraph (graph/workflow)    │
  │  START → vision → evidence → reproduction    │
  │       → recall → investigator → regression   │ ──► Gradio UI / 冒烟
  └──────────────────────────────────────────────┘
        │                                          ▲
        ▼  统一 OpenAI 兼容（本地优先+远程fallback） │
  ┌─────────────┐  :8000 文本   :8001 VL   :8002 bge │
  │  DGX Spark  │ ◄────────────────────────────────┘
  └─────────────┘   远程 stepfun 作 fallback
```

### 5.2 数据流要点
- **Bug 是否复现是跑出来的**（Playwright 真实回放 + 连跑 3 次判稳定），不靠 LLM 嘴说；
- **所有 LLM 调用**经 `llm/client.py` 统一抽象，本地优先 + 远程 fallback；
- **vision / recall 可选 + 降级**：任一关闭或失败，主流水线照跑。

### 5.3 模块组成
`agents/`（6 节点）· `graph/`（编排）· `memory/`（RAG）· `capture/`（录制+视频）· `test_runner/`（Playwright）· `code_search/`（检索）· `minimization/`（最小复现）· `llm/`（模型抽象）· `asr/` · `ui/` · `eval/` · `deploy/spark71/`（三服务部署）· `tests/`。详见 [`docs/模块架构.md`](docs/模块架构.md)。

---

## 六、验证与评测

| 项 | 结果 |
|---|---|
| 单元测试 | 85 passed（全 mock）/ 1 skipped；覆盖 config/client/store/vision/recall/workflow 等 |
| 端到端冒烟 | smoke_phase3（主流程）/ smoke_vl（本地 Qwen2.5-VL 看图 confidence 1.00）/ smoke_rag（本地 bge 命中）/ smoke_fallback（本地挂→远程兜底 0.95）|
| 三服务部署 | spark-71 文本推理✓ / VL 看图✓ / bge embedding✓，峰值显存 ~108GB/119GB |
| 演示场景 | 商城 Bug1（优惠券不随数量更新）稳定复现：apply 后 80，改数量 2 仍 80（应 160）|
| **回归闭环** | 同一测试 **buggy 失败**（actual 80）、**fixed 通过**（actual 160）——商城 `?fixed=1` 切修复版验证，最强的「Bug 复现 + 修复验证」证明 |

> 冒烟驱动：多个 mock 测不出的真实 bug（代码围栏 / 漏 import / 路径正则 / VL 启动参数 / 显存共存）都由真调端到端冒烟发现并修复——AI 写的代码必须真跑。

---

## 七、团队分工与贡献

**taostronger 队**（按单人 MVP 设计，每功能配降级）

| 成员 | 贡献 |
|---|---|
| **tz**（队长）| 整体架构；6 节点 Agent；最小复现算法；VL 视觉；RAG 记忆；操作采集（Playwright）；视频输入；本地为主+远程 fallback 模型层；spark-71 三服务部署（vLLM + bge）；测试 + 冒烟；文档 |
| **liwenY**（队员）| 商城 Bug 场景设计与素材；Demo 视频录制与剪辑；审美把控；路演协助 |

---

## 八、未来展望

- **自动截图采集**：接 capture / reproduction 失败截图，去掉手动上传；
- **CI / GitHub Actions 集成**：生成的回归测试自动接入持续集成；
- **记忆库治理**：去重、过期、重排、混合检索，提升 RAG 质量；
- **多语言 / 多框架**：当前 Playwright + TypeScript，扩展 Python / Java 测试生成；
- **产品化**：VL 接自动截图、RAG 加管理 UI，作为完整产品方向。

---

## 九、文档索引

| 文档 | 内容 |
|---|---|
| [需求分析](docs/需求分析.md) | 问题背景、目标用户、功能 / 非功能需求、典型场景 |
| [使用方式](docs/使用方式.md) | 环境准备、配置、运行、四种输入、输出解读、FAQ |
| [架构与部署](docs/架构与部署.md) | 系统架构、数据流、双轨 + fallback、spark-71 三服务部署实测 |
| [裸机部署](docs/裸机部署.md) | **从零部署清单**：DGX Spark 三服务 + 本地 ReproForge，含精确版本+实测坑+命令 |
| [模块架构](docs/模块架构.md) | 各模块职责、接口、依赖、协同 |

---

*NVIDIA DGX Spark 多模态 Agent 黑客松 · 2026 · taostronger 队*
