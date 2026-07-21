# ReproForge VL 视觉 + RAG 记忆 设计

> 日期：2026-07-21 · 状态：已批准，待开发 · 作者：tz（taostronger 队）
> 目标提交：预赛 7.22（极简 + 强降级，任一功能挂掉主流水线照跑）

---

## 1. 背景与目标

ReproForge 当前是「文本+操作」驱动：evidence 只从**口述文本**提 expected/actual，code_investigator 只做**无状态**检索打分。两个短板：

1. **缺多模态**：赛题是「多模态 Agent」，当前只有语音(whisper)+操作(Playwright)+文本(LLM)，**没有视觉**。`capture/recorder.py` 已经在录 trace 截图（`screenshots=True`），但**完全没用上**。
2. **无记忆**：每次复现都是独立的，不会参考历史 Bug 经验。往届获奖项目（Starfire/DetectiveRAG）的共同特征是**多 Agent + RAG/知识库**。

本设计加两个**可独立开关、可独立降级**的子系统：

| 功能 | 一句话 | 补的短板 |
|---|---|---|
| **VL 视觉**（vision agent）| 看一张 Bug 截图，提 expected/actual，辅助 evidence | 多模态（视觉）|
| **RAG 记忆**（recall agent + memory store）| 历史 Bug 入向量库，新 Bug 检索相似案例辅助 investigator | 记忆/知识库 |

---

## 2. 非目标（预赛 7.22 明确不做）

为保明天能上线，以下**全部留给决赛**：

- ❌ 自动截图采集（接 capture trace 提取 / 增强 test_runner 提取 Playwright 失败截图）—— 预赛 VL 走**用户手动上传截图**
- ❌ 本地 VL 模型（Qwen2.5-VL）部署 —— 预赛 VL 走**远程 step-3.7 多模态**，本地决赛补
- ❌ RAG 向量库调优（重排、混合检索）—— 预赛用 bge-large-zh 单路检索 Top-3
- ❌ 记忆库管理 UI / 去重 / 过期 —— 预赛只 ingest + query
- ❌ 多 Agent 并行编排 —— 流水线保持线性，只新增两个串行节点

---

## 3. 整体架构

新流水线（LangGraph StateGraph，线性，新增 `vision` 和 `recall` 两个节点）：

```
START
  │
  ▼
[vision]      ← 新：看截图(step-3.7多模态) 提 expected/actual/page_desc     （无图则跳过）
  │
  ▼
[evidence]    ← 改：综合 vision 的视觉提取 + 口述提取
  │
  ▼
[reproduction]
  │
  ▼
[recall]      ← 新：检索历史相似 Bug（chromadb+bge）Top-3                   （库空则跳过）
  │
  ▼
[investigator]← 改：prompt 注入「相似历史 Bug 参考」段
  │
  ▼
[regression]  ← 改：生成 Issue 后 ingest 进记忆库
  │
  ▼
END
```

**关键不变量**：vision 和 recall 都是「可选输入 + try/except 全包 + 失败返回空」，**移除这两个节点后流水线必须仍能跑通**（= 现有版本）。这是降级的底线。

---

## 4. VL 视觉详细设计

### 4.1 新文件：`agents/vision.py`

```python
from dataclasses import dataclass

@dataclass
class VisualFinding:
    expected: str = ""
    actual: str = ""
    page_description: str = ""   # VL 对页面状态的客观描述
    confidence: float = 0.0      # 0-1，VL 自评
    needs_confirm: bool = False
    used: bool = False           # 是否真的用了视觉（无图/失败为 False）


def analyze_screenshot(screenshot, narration) -> VisualFinding:
    """看截图 + 口述，调 step-3.7 多模态提 expected/actual/page_description。

    screenshot: 图片路径（本地）或 URL 或 None。
    narration: 测试员口述文本。
    返回 VisualFinding；无截图 / 调用失败 → 返回空 finding（used=False，evidence 照旧）。
    """
    if not screenshot:
        return VisualFinding()                      # 无图，降级
    image_data_uri = _to_data_uri(screenshot)       # 本地文件 → base64 data URI
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": _VL_PROMPT.format(narration=narration)},
            {"type": "image_url", "image_url": {"url": image_data_uri}},
        ],
    }]
    try:
        result = chat_vision(messages)              # llm/client 新增
        return VisualFinding(
            expected=result.get("expected", ""),
            actual=result.get("actual", ""),
            page_description=result.get("page_description", ""),
            confidence=float(result.get("confidence", 0.0)),
            needs_confirm=float(result.get("confidence", 0.0)) < 0.6,
            used=True,
        )
    except Exception:
        return VisualFinding()                      # 任何失败都降级
```

`_VL_PROMPT`（让 VL 输出 JSON）：
```
你是测试工程师。这是一张 Bug 截图，测试员口述：{narration}。
请看图提取：预期值、实际值（页面实际显示）、页面状态描述、置信度(0-1)。
只输出 JSON：{"expected":"...","actual":"...","page_description":"...","confidence":0.0}
若图里看不清关键信息，confidence 给低分。
```

### 4.2 `llm/client.py` 扩展：`chat_vision`

当前 `chat()` 只处理 text message。新增 `chat_vision(messages)`，接受 content 为 `list`（text + image_url）的多模态 message，其余复用现有 OpenAI 兼容客户端 + `chat_json` 的 JSON 提取逻辑。

```python
def chat_vision(messages, model=None):
    """多模态调用（content 可含 image_url）。复用 _get_client()，temperature=0.1。"""
    content = chat(messages, model=model, temperature=0.1)   # chat 已支持 messages 透传
    match = re.search(r'\{.*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in vision response")
```
> 现有 `chat()` 直接把 messages 透传给 `client.chat.completions.create`，OpenAI 兼容接口本身支持 content 为 list，**chat() 无需改动**，只需新增上面的 JSON 解析包装。

### 4.3 图片转 data URI：`_to_data_uri`

本地截图文件要转 base64 data URI（远程 step-3.7 访问不了本地 file://）：

```python
def _to_data_uri(screenshot):
    if screenshot.startswith(("http://", "https://", "data:")):
        return screenshot                           # 已是 URL/data URI
    import base64, mimetypes
    with open(screenshot, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = mimetypes.guess_type(screenshot)[0] or "image/png"
    return f"data:{mime};base64,{b64}"
```

### 4.4 evidence 协同（合并策略）

`agents/evidence.py` 的 `build_timeline` 改为接收 `visual_finding`，合并 expected/actual：

- **优先级**：`visual_finding.confidence >= 口述 confidence` → 用 vision 的；否则用口述的
- **冲突**（两者都有但值不同）→ `needs_confirm = True`（转人工确认，沿用现有降级语义）
- **vision 未用**（used=False）→ 完全走口述（现有逻辑零改动）

### 4.5 UI 改动：`ui/app.py`

- 加 `gr.Image(label="Bug 截图（可选）", type="filepath")` 上传框
- `run_pipeline_ui` 把截图路径透传给 `run_pipeline(screenshot=...)`
- 结果区可选展示 `visual_finding`（让评委看到 VL 看出了什么）

### 4.6 降级链

| 触发 | 行为 |
|---|---|
| 未上传截图 | `analyze_screenshot` 返回空，evidence 走口述 |
| step-3.7 不支持图像（开发第一步验证）| VL 整体降级，文档标注决赛换本地 Qwen2.5-VL |
| 调用超时/返回非 JSON | `try/except` 返回空，evidence 走口述 |

---

## 5. RAG 记忆详细设计

### 5.1 新文件：`memory/store.py`

chromadb 持久化封装，bge-small-zh 做 embedding：

```python
import uuid
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

class MemoryStore:
    def __init__(self, path="./reproforge_memory"):
        self.client = chromadb.PersistentClient(path=path)
        self.ef = SentenceTransformerEmbeddingFunction(
            model_name="BAAI/bge-large-zh-v1.5"      # HF 下载，复用 whisper 的镜像环境变量
        )
        self.col = self.client.get_or_create_collection(
            "bug_issues", embedding_function=self.ef)

    def ingest_issue(self, issue, timeline, top_files):
        """Issue 入库。文档=expected+actual+可疑文件名+testid；metadata=minimal_steps/stable_rate。"""
        testids = " ".join(e.target for e in timeline.events if e.target)
        doc = f"预期 {timeline.expected} 实际 {timeline.actual} "
        doc += " ".join(issue.suspected_files) + " " + testids
        self.col.add(
            documents=[doc],
            metadatas=[{"expected": timeline.expected, "actual": timeline.actual,
                        "suspected": ",".join(issue.suspected_files),
                        "minimal_steps": " | ".join(issue.minimal_steps),
                        "stable_rate": issue.stable_rate}],
            ids=[str(uuid.uuid4())],                 # uuid 避免重复
        )

    def query_similar(self, timeline, actions, top_k=3):
        """检索相似历史 Bug。返回 [{doc, metadata, distance}]，空库返回 []。"""
        if self.col.count() == 0:
            return []                                # 冷启动
        testids = " ".join(e.target for e in timeline.events if e.target)
        query = f"预期 {timeline.expected} 实际 {timeline.actual} {testids}"
        res = self.col.query(query_texts=[query], n_results=top_k)
        return [{"doc": res["documents"][0][i], "metadata": res["metadatas"][0][i],
                 "distance": res["distances"][0][i]}
                for i in range(len(res["documents"][0]))]
```

> bge-large-zh-v1.5 通过 sentence-transformers 从 HF 下载（~1.3GB，质量优于 small），**复用 `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`**（和 faster-whisper 同一套，已在 day1-spike 验证可用）。

### 5.2 新文件：`agents/recall.py`

```python
from dataclasses import dataclass, field

@dataclass
class HistoricalRef:
    items: list = field(default_factory=list)   # query_similar 的结果
    used: bool = False                          # 是否真的用了记忆

def recall(timeline, actions, store=None) -> HistoricalRef:
    """检索相似历史 Bug。store 为 None / 库空 / 失败 → 返回空，investigator 照旧。"""
    if store is None:
        return HistoricalRef()
    try:
        items = store.query_similar(timeline, actions, top_k=3)
        return HistoricalRef(items=items, used=bool(items))
    except Exception:
        return HistoricalRef()                     # 降级
```

### 5.3 investigator 改动（注入历史参考）

`agents/code_investigator.py` 的 `investigate` 接收 `historical_ref`，在 `_RANK_PROMPT` 里加一段「相似历史 Bug 参考」：

```
相似历史 Bug 参考（仅作线索，不视为结论）：
{historical_ref.items 的 doc/metadata 摘要}
```
让 LLM 打分时参考历史可疑文件。冷启动（items 空）时这段为空，等同现有逻辑。

### 5.4 regression 改动（ingest 记忆）

`run_pipeline` 跑完 regression 生成 Issue 后，调用 `store.ingest_issue(issue, timeline, top_files)` 把本次 Bug 入库。ingest 失败 try/except 跳过（不影响 Issue 输出）。

### 5.5 降级链

| 触发 | 行为 |
|---|---|
| chromadb 未装 / 初始化失败 | store=None，recall 返回空，investigator 照旧 |
| bge 模型下载失败 | 同上 |
| 库空（首次跑） | `query_similar` 返回 []，冷启动正常 |
| ingest 失败 | 跳过，Issue 照常输出 |

---

## 6. LangGraph 工作流改动（`graph/workflow.py`）

State 扩展 3 个字段：

```python
class State(TypedDict, total=False):
    # ... 现有字段 ...
    screenshot: Optional[str]      # UI 上传的截图路径/URL
    visual_finding: Any            # vision 输出
    historical_ref: Any            # recall 输出
```

新增两个节点 + 改两条边：

```python
def vision_node(state):
    vf = analyze_screenshot(state.get("screenshot"),
                            " ".join(getattr(s, "text", "") for s in state["segments"]))
    return {"visual_finding": vf}

def recall_node(state):
    store = get_memory_store()                     # 从环境变量/配置构造，失败返回 None
    ref = recall(state["timeline"], state["actions"], store=store)
    return {"historical_ref": ref}

# 边
g.add_edge(START, "vision")
g.add_edge("vision", "evidence")
g.add_edge("reproduction", "recall")
g.add_edge("recall", "investigator")
# evidence 接收 visual_finding；investigator 接收 historical_ref
# regression 后 ingest_issue（在 regression_node 末尾或 run_pipeline 末尾）
```

`run_pipeline` 签名加 `screenshot=None`。

---

## 7. 配置（`config.py` + 环境变量）

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `REPROFORGE_VL` | `on` | VL 开关（off 则 vision 节点直接返回空）|
| `REPROFORGE_MEMORY` | `on` | RAG 开关（off 则 recall 节点直接返回空、不 ingest）|
| `REPROFORGE_MEMORY_PATH` | `./reproforge_memory` | chromadb 持久化目录 |
| `HF_ENDPOINT` / `HF_HUB_DISABLE_XET` | hf-mirror / 1 | bge 模型下载（复用 whisper 设置）|

---

## 8. 降级总表（两功能都不阻塞主流水线）

| 场景 | vision | recall | 主流水线 |
|---|---|---|---|
| 正常 | ✅ 看图提结论 | ✅ 检索历史 | 全流程 |
| 无截图 | 跳过 | — | evidence 走口述 |
| step-3.7 图像不支持 | 跳过 | — | evidence 走口述 |
| chromadb 未装 | — | 跳过 | investigator 无历史参考 |
| 库空（首次）| — | 返回空 | investigator 无历史参考（冷启动）|
| 任一异常 | try/except 返回空 | try/except 返回空 | **照常输出 Issue** |

---

## 9. 测试策略

| 测试文件 | 覆盖 | 手段 |
|---|---|---|
| `tests/test_vision.py` | message 构造、VisualFinding 解析、无图/失败降级 | mock `chat_vision` |
| `tests/test_store.py` | ingest 写入、query 返回、冷启动空 | mock chromadb collection |
| `tests/test_recall.py` | store=None 降级、空库降级、Top-K 注入 | mock `MemoryStore` |
| `tests/test_workflow.py`（扩展）| vision/recall 节点接入、State 流转、移除两节点仍跑通 | 现有 mock 套路 |
| `spike/smoke_vl_rag.py`（新）| 真调 step-3.7 图像 + 真 chromadb 检索 | 端到端冒烟（预跑验证用）|

真调留冒烟（和现有 smoke_phase3 同套路），单测全 mock。

---

## 10. 开发顺序与里程碑

**VL 先**（~半天，补多模态短板，优先级高）：

1. **验证 step-3.7 图像能力**（30 分钟，最先做，决定 VL 可行性）：发一个带 image_url 的 chat 请求，确认能返回图像理解。不支持则 VL 降级、转决赛。
2. `llm/client.py` 加 `chat_vision`（含 data URI helper）
3. `agents/vision.py`（VisualFinding + analyze_screenshot + 降级）
4. `graph/workflow.py` 接 vision 节点 + State 加字段
5. `agents/evidence.py` 合并 visual_finding
6. `ui/app.py` 加截图上传
7. `tests/test_vision.py` + 扩展 test_workflow
8. 冒烟：`spike/smoke_vl_rag.py` 真调一次

**RAG 后**（~1 天）：

1. `pip install chromadb sentence-transformers` + 下 bge-large-zh（hf-mirror，~1.3GB）
2. `memory/store.py`（MemoryStore）
3. `agents/recall.py`（HistoricalRef + recall）
4. `graph/workflow.py` 接 recall 节点
5. `agents/code_investigator.py` 注入历史参考
6. regression 末尾 ingest_issue
7. `tests/test_store.py` + `test_recall.py`
8. 冒烟：跑两次（第二次应检索到第一次的历史）

**里程碑**：VL 跑通 = 多模态补齐（可演示）；RAG 跑通 = 记忆链路完整。**任一未完成都不阻塞预赛提交**（主流水线不依赖）。

---

## 11. 风险与回退

| 风险 | 应对 |
|---|---|
| step-3.7-flash 不支持图像输入 | 开发第一步验证；不支持 → VL 降级（vision 节点返回空），决赛换本地 Qwen2.5-VL |
| chromadb / sentence-transformers 装不上或 bge 下载卡 | RAG 降级（store=None）；预赛保 VL，RAG 转决赛 |
| bge 中文检索质量差 | 已用 large（质量好）；决赛可加重排/混合检索 |
| 时间不够两个都做完 | VL 优先（多模态加分 > 记忆加分）；RAG 做不完就 `REPROFORGE_MEMORY=off` 关掉 |

**回退兜底**：两个功能都用环境变量开关，`off` 后 `workflow` 里对应节点直接返回空，等于现有版本。**最坏情况 = 现有预赛版本，零退化**。

---

## 12. 双轨与赛后

- **VL 双轨**：预赛远程 step-3.7 多模态 / 决赛补本地 Qwen2.5-VL（vLLM 第二实例，util 调 0.4 腾显存）。复用 `config.py` PROFILE 机制。
- **RAG**：embedding 本地 bge、记忆库本地 chromadb，**天然本地**，不依赖远程。
- 赛后：VL 可接 capture 自动截图（去掉手动上传）、RAG 可加去重/过期/重排，作为产品化方向。
