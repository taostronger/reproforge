# ReproForge bge 迁移 spark-71 + VL 本地双轨 + 远程 fallback 加固 设计

> 日期：2026-07-22 · 状态：已批准，待实施 · 作者：tz（taostronger 队）
> 目标：决赛 8.2 路演前，把 RAG embedding 与 VL 视觉全部下沉到 spark-71 本地算力，并以远程 Stepfun API 作极端兜底，实现「全本地为主 + 远程加固」。

---

## 1. 背景与目标

预赛版 ReproForge 有两处「远程依赖 / 设计缺陷」（见 `docs/项目状态.md` 待办 1、2）：

1. **RAG bge 本地化是缺陷**：`memory/store.py` 用 `SentenceTransformerEmbeddingFunction` 在**用户演示机本地**下载并加载 bge-large-zh（要 torch/sentence-transformers）。演示机不该扛 torch 这么重的依赖——这是设计缺陷。
2. **VL 全远程**：`get_vl_model_config()` 写死远程 step-3.7，没有本地 VL 能力。赛题是「多模态 Agent + 本地算力部署」，VL 必须有本地路径。

本设计把两者下沉到 spark-71，并新增一层**远程 fallback 加固**：

| 改造 | 目标 |
|---|---|
| **bge 迁 spark-71** | spark-71 起 bge embedding 服务，本地 chromadb 调远程 EF；演示机只留 chromadb+requests，不再装 torch |
| **VL 本地双轨** | spark-71 vLLM 第二实例跑 Qwen2.5-VL-7B，`chat_vision` 本地优先 |
| **远程 fallback 加固** | 文本/VL 本地实例挂了/超时/连不上 → 自动降级远程 stepfun，保证演示不中断 |

**核心不变量**（沿用 ReproForge 降级哲学）：三服务任一挂掉，主流水线照跑。最坏情况退化为现有预赛版本（纯远程 + RAG off），零退化。

---

## 2. 非目标

- ❌ bge 检索质量调优（重排 / 混合检索）—— 仍 bge-large-zh 单路 Top-3
- ❌ 记忆库管理 UI / 去重 / 过期 —— 不变
- ❌ 三服务做成 systemd 自启 / 容器编排 —— 黑客松用 shell 脚本手动起，够用
- ❌ 文本 LLM 也做 fallback 之外的负载均衡 —— 单本地 + 单远程，不做多副本
- ❌ VL 自动截图采集 —— 仍用户手动上传截图（决赛另议）

---

## 3. 决策汇总（已与队长确认）

1. **范围**：全链路端到端（代码改造 + SSH 到 spark-71 下模型/起服务/本地端到端验证）
2. **显存共存**：双实例都降 util，峰值 ~111GB（不占满 119GB，留 ~8GB 系统）
3. **架构**：本地为主 + 远程 stepfun 作极端 fallback（服务加固）
4. **bge 服务栈**：sentence-transformers + FastAPI（OpenAI 兼容 `/v1/embeddings`）
5. **VL 模型**：Qwen2.5-VL-7B-Instruct

---

## 4. 整体架构

### 4.1 spark-71 三服务（单 GB10，统一内存 119GB）

| 服务 | 端口 | 模型 | util | 实占估算 | 说明 |
|---|---|---|---|---|---|
| 文本 vLLM | :8000 | qwen36-35b-a3b（已有） | **0.45**（从 0.8 降） | ~59GB | 35B 权重~35G + KV~24G，单用户演示够 |
| VL vLLM | :8001 | Qwen2.5-VL-7B-Instruct（新下） | **0.4** | ~52GB | 7B 权重~15G + KV~37G，富余 |
| bge 服务 | :8002 | bge-large-zh-v1.5（新下） | —（CPU） | **0 显存** | 推理轻，CPU 单条几十 ms，不和 GPU 抢显存 |
| **峰值合计** | | | | **~111GB** | 留 ~8GB 给系统 |

> 显存精算依据：文档实测 util 0.8 实占 105GB，即 vLLM 实际占用 ≈ `util × 119 × 1.1`。故 `0.45×119×1.1 ≈ 59` + `0.4×119×1.1 ≈ 52` = 111GB。bge 走 CPU 是峰值可控的关键。文本从 0.5 再压到 0.45 以留余量。

### 4.2 调用模型：本地优先 + 远程 fallback

```
chat() / chat_json()        文本
   ├─ 1) 试 本地 vLLM :8000（超时 60s）
   └─ 2) 连不上/超时/5xx → fallback 远程 stepfun step-3.7
chat_vision()               VL
   ├─ 1) 试 本地 vLLM :8001 Qwen2.5-VL（超时 120s）
   └─ 2) 失败 → fallback 远程 stepfun step-3.7 多模态
store.py embedding          RAG
   └─ 调 本地 bge 服务 :8002（连不上 → get_memory_store 返回 None，recall 降级）
```

**开发态**（不设 `LOCAL_*`）：纯远程 stepfun，行为完全等同现有预赛版（零改动）。
**演示态**（设 `LOCAL_*` + 隧道）：本地优先，远程兜底。

### 4.3 三服务均 OpenAI 兼容，本地经 SSH 隧道访问

spark-71 公网只映射了 SSH(6071)/Jupyter(8071)，:8000/:8001/:8002 无公网映射 → 本地经 SSH 隧道转发三端口到 localhost（沿用 `ssh信息/spark-71-连接指南.md` 的 sshtunnel 套路）。

---

## 5. bge embedding 服务（spark-71）

### 5.1 新文件 `~/reproforge_serve/bge_server.py`（~40 行 FastAPI）

OpenAI 兼容 `/v1/embeddings`，CPU 加载 bge-large-zh-v1.5：

```python
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()
_model = SentenceTransformer("/home/Developer/models/bge-large-zh-v1.5", device="cpu")

class EmbReq(BaseModel):
    input: list[str]
    model: str = "bge-large-zh"

@app.post("/v1/embeddings")
def embeddings(req: EmbReq):
    vecs = _model.encode(req.input, normalize_embeddings=True).tolist()
    return {"data": [{"embedding": v} for v in vecs], "model": req.model}

@app.get("/v1/models")
def models():
    return {"data": [{"id": "bge-large-zh"}]}
```

启动：`uvicorn bge_server:app --host 0.0.0.0 --port 8002`（CPU，不占 GPU）。

> 复用 spark-71 的 `~/build_a_claw_workshop-bundle/comfyui-env`（torch 2.11 + transformers 5.5）跑；或用系统 Python 装 `sentence-transformers fastapi uvicorn`（bge 走 torch CPU，不经 comfyui-env 也行，实测择优）。

---

## 6. `memory/store.py` 改造（去 torch 依赖）

### 6.1 `RemoteEmbeddingFunction`（新增，符合 chromadb EF 协议）

```python
import requests

class RemoteEmbeddingFunction:
    """调 spark-71 bge 服务的 /v1/embeddings，符合 chromadb embedding function 协议。"""
    def __init__(self, base_url, model="bge-large-zh", timeout=30):
        self.base_url, self.model, self.timeout = base_url, model, timeout

    def __call__(self, input: list[str]) -> list[list[float]]:
        # chromadb 0.5+ 要求 __call__ 带 (input: Documents) -> Embeddings 类型注解，否则告警/报错
        resp = requests.post(f"{self.base_url}/v1/embeddings",
                             json={"input": input, "model": self.model},
                             timeout=self.timeout)
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]
```

### 6.2 `MemoryStore.__init__` 改用远程 EF

```python
class MemoryStore:
    def __init__(self, path=None):
        self.path = path or os.getenv("REPROFORGE_MEMORY_PATH", "./reproforge_memory")
        ef_url = os.getenv("EMBEDDING_BASE_URL")                 # spark-71 bge（经隧道）
        if not ef_url:
            raise RuntimeError("无 EMBEDDING_BASE_URL，远程 embedding 不可用")
        self.client = chromadb.PersistentClient(path=self.path)
        self.ef = RemoteEmbeddingFunction(ef_url)
        self.col = self.client.get_or_create_collection("bug_issues", embedding_function=self.ef)
```

> 删除对 `SentenceTransformerEmbeddingFunction` 的依赖。`ingest_issue` / `query_similar` / `list_all` 方法体不变（它们只调 `self.col.add/query/get`，与 EF 无关）。

### 6.3 降级链（不变）

- `EMBEDDING_BASE_URL` 未设 / bge 服务没起 / 初始化失败 → `get_memory_store()` 返回 None → recall 返回空 → investigator 照旧
- 运行时 bge 挂了 → `query_similar` 抛异常 → 业务层 recall `try/except` 降级

---

## 7. `config.py` 双轨拆分

保留旧函数向后兼容（`eval/compare.py` 仍用 `get_model_config()`），新增本地/远程拆分：

```python
@dataclass
class ModelConfig:
    base_url: str
    model: str
    api_key: str
    is_local: bool = False

# —— 文本 ——
def get_local_model_config() -> ModelConfig | None:
    """有 LOCAL_BASE_URL → 本地 vLLM（spark-71 :8000）；否则 None。"""
    if os.getenv("LOCAL_BASE_URL"):
        return ModelConfig(os.getenv("LOCAL_BASE_URL"),
                           os.getenv("LOCAL_MODEL", "qwen2.5-coder:7b"),
                           os.getenv("LOCAL_API_KEY", "ollama"), is_local=True)
    return None

def get_remote_model_config() -> ModelConfig:
    """远程 stepfun step-3.7。"""
    return ModelConfig("https://api.stepfun.com/step_plan/v1",
                       os.getenv("STEPFUN_MODEL", "step-3.7-flash"),
                       os.environ["STEPCONFIG_FUN_API_KEY"])

# —— VL ——
def get_local_vl_config() -> ModelConfig | None:
    """有 LOCAL_VL_BASE_URL → 本地 vLLM Qwen2.5-VL（spark-71 :8001）；否则 None。"""
    if os.getenv("LOCAL_VL_BASE_URL"):
        return ModelConfig(os.getenv("LOCAL_VL_BASE_URL"),
                           os.getenv("LOCAL_VL_MODEL", "Qwen2.5-VL-7B-Instruct"),
                           os.getenv("LOCAL_VL_API_KEY", "vllm"), is_local=True)
    return None

def get_remote_vl_config() -> ModelConfig:
    """远程 stepfun step-3.7 多模态。"""
    return ModelConfig("https://api.stepfun.com/step_plan/v1",
                       os.getenv("VL_MODEL", "step-3.7-flash"),
                       os.environ["STEPCONFIG_FUN_API_KEY"])

# get_model_config() / get_vl_model_config() 保留，行为不变（返回"主配置"），不破坏现有调用
```

---

## 8. `llm/client.py` fallback（核心）

### 8.1 统一 fallback 包装

```python
import logging, httpx
from openai import APIConnectionError, APITimeoutError, InternalServerError

log = logging.getLogger("reproforge.llm")
_LOCAL_TIMEOUT = 60      # 文本本地
_VL_LOCAL_TIMEOUT = 120  # VL 本地（图像慢）

def _call(cfg, messages, temperature, timeout, model=None):
    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=timeout)
    resp = client.chat.completions.create(
        model=model or cfg.model, messages=messages, temperature=temperature)
    content = resp.choices[0].message.content
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()  # 剥 thinking（qwen3.6）
    if '</think>' in content:
        content = content.split('</think>')[-1].strip()
    return content

def _chat_with_fallback(messages, local, remote, temperature, timeout, model=None):
    """本地优先；失败（服务不可用类）→ fallback 远程；都失败 raise。"""
    if local:
        try:
            return _call(local, messages, temperature, timeout, model)
        except (APIConnectionError, APITimeoutError, InternalServerError,
                httpx.ConnectError, httpx.TimeoutException) as e:
            log.warning("[fallback] 本地 %s 失败(%s) → 切远程", local.base_url, type(e).__name__)
    return _call(remote, messages, temperature, timeout, model)
```

### 8.2 `chat` / `chat_json` / `chat_vision` 改造

```python
def chat(messages, model=None, temperature=0.3):
    content = _chat_with_fallback(messages, get_local_model_config(), get_remote_model_config(),
                                  temperature, _LOCAL_TIMEOUT, model=model)
    return content

def chat_json(messages, model=None):
    content = chat(messages, model=model, temperature=0.1)
    match = re.search(r'\{.*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")

def chat_vision(messages, model=None):
    content = _chat_with_fallback(messages, get_local_vl_config(), get_remote_vl_config(),
                                  0.1, _VL_LOCAL_TIMEOUT, model=model)
    match = re.search(r'\{.*\}', content, re.S)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in vision response")
```

### 8.3 fallback 触发条件（关键约束）

| 异常 | 触发 fallback？ | 理由 |
|---|---|---|
| `APIConnectionError` / `httpx.ConnectError`（连不上） | ✅ | 本地服务挂了 |
| `APITimeoutError` / `httpx.TimeoutException`（超时） | ✅ | 本地卡住 |
| `InternalServerError`（5xx） | ✅ | 本地 vLLM 内部错 |
| `BadRequestException`（4xx 参数错） | ❌ | 远程也会同样报错，兜底无意义 |
| `AuthenticationException`（鉴权） | ❌ | 同上 |
| 正常返回 | — | 直接用本地结果，不触远程 |

> `_client` 单例缓存移除（fallback 需要两个独立 client，按 cfg 即时构造；切 PROFILE 时不再需要手动 reset `_client=None`）。

---

## 9. spark-71 部署脚本（新建 `~/reproforge_serve/`）

⚠️ **流量计费**：模型全程在 spark-71 用 `huggingface-cli download`（走 hf-mirror 内网），**严禁 scp 上传**。

### 9.1 `download_models.sh`

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct --local-dir ~/models/Qwen2.5-VL-7B-Instruct
huggingface-cli download BAAI/bge-large-zh-v1.5       --local-dir ~/models/bge-large-zh-v1.5
```

### 9.2 `serve_text_vllm.sh`（文本，util 0.45）

```bash
docker run -d --name vllm-text --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models eugr/spark-vllm:latest \
  vllm serve /models/qwen36-35b-a3b --host 0.0.0.0 --port 8000 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.45 \
    --max-model-len 8192 --max-num-batched-tokens 4096 \
    --load-format fastsafetensors --kv-cache-dtype fp8 --enable-prefix-caching
```

### 9.3 `serve_vl_vllm.sh`（VL，util 0.4）

```bash
docker run -d --name vllm-vl --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models eugr/spark-vllm:latest \
  vllm serve /models/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8001 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.4 \
    --max-model-len 8192 --limit-mm-per-prompt image=1 \
    --max-num-batched-tokens 4096 --enable-prefix-caching
```

> Qwen2.5-VL 已合入 transformers 5.5（spark-71 comfyui-env 有），无需 `--trust-remote-code`。`--limit-mm-per-prompt image=1` 参数名按 vLLM 0.23.1rc1 实测调整（新版可能为 `--limit-mm-per-request`）。**VL 启动参数列为实测验证项**（§12）。

### 9.4 `serve_bge.sh`（bge，CPU）

```bash
cd ~/reproforge_serve
nohup uvicorn bge_server:app --host 0.0.0.0 --port 8002 > bge.log 2>&1 &
```

### 9.5 `start_all.sh`

按序起 3 服务 + 健康检查：

```bash
bash serve_text_vllm.sh; bash serve_vl_vllm.sh; bash serve_bge.sh
# 健康检查（启动预热需 2-3 分钟）
for p in 8000 8001 8002; do curl -s http://localhost:$p/v1/models || echo "port $p not ready"; done
```

---

## 10. 本地隧道 + 环境变量

### 10.1 `scripts/tunnel.sh`（本地新建，三端口隧道）

```bash
ssh -p 6071 -N \
  -L 8000:localhost:8000 \
  -L 8001:localhost:8001 \
  -L 8002:localhost:8002 \
  Developer@106.13.186.155
```

> 或用 `ssh信息` 文档里的 sshtunnel（Python）三端口版。

### 10.2 `.env` 追加（演示态）

```
STEPCONFIG_FUN_API_KEY=（已有，远程 fallback 用）
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL=/models/qwen36-35b-a3b
LOCAL_VL_BASE_URL=http://localhost:8001/v1
LOCAL_VL_MODEL=/models/Qwen2.5-VL-7B-Instruct
EMBEDDING_BASE_URL=http://localhost:8002
```

> 开发态不设 `LOCAL_*` → 自动纯远程（现有行为）。`PROFILE` 环境变量逐步退役（由 `LOCAL_*` 是否存在决定本地路径），但 `get_model_config()` 仍兼容 `PROFILE=local` 以不破坏 `eval/compare.py`。

---

## 11. 测试策略

| 文件 | 覆盖 | 手段 |
|---|---|---|
| `tests/test_store.py`（改） | RemoteEF ingest/query/冷启动/降级 | mock `requests.post`（替代 mock `SentenceTransformerEmbeddingFunction`）；ingest/query/空库/get_memory_store 降级断言不变 |
| `tests/test_client.py`（**新增**） | fallback 链 | mock `_call`：本地抛 `APIConnectionError`→验证走远程且只 1 次；本地成功→不触远程；本地+远程都失败→raise；4xx 不触发 fallback |
| `tests/test_vision.py`（不变） | analyze_screenshot / _to_data_uri | mock `chat_vision`（接口未变，内部 fallback 透明） |
| `tests/test_config.py`（**新增**） | 四个 get_*_config 的 None/返回逻辑 | 设/不设 `LOCAL_*` 环境变量 |
| `spike/smoke_vl.py`（改） | 真调本地 Qwen2.5-VL 看图 | 设 `LOCAL_VL_BASE_URL` 跑 |
| `spike/smoke_rag.py`（改） | 真调本地 bge 远程 embedding | 设 `EMBEDDING_BASE_URL` 跑 |
| `spike/smoke_fallback.py`（**新增**） | 真验证 fallback | 停本地 VL → chat_vision 仍成功（走远程） |

单测全 mock；真调留冒烟（和现有 smoke_phase3 同套路）。

---

## 12. 风险与回退

| 风险 | 应对 |
|---|---|
| Qwen2.5-VL 在 vLLM 0.23.1rc1 / GB10 启动失败 | §9.3 启动参数实测；失败 → VL fallback 远程 step-3.7（演示不中断），降优先级排查 |
| 双实例 util 0.45+0.4 仍 OOM | bge 已走 CPU；再降文本到 0.4 / VL 到 0.35；极端情况二选一跑（文本走远程，只起 VL） |
| bge 服务 CPU 慢拖累 RAG | RAG 非热路径（每 Bug 才 ingest/query 一次）；慢 → recall 超时降级，不阻塞主流水线 |
| 远程 fallback 也失败（断网） | client raise → 业务层 try/except 降级（evidence 走口述 / vision 返回空 / recall 返回空），主流水线照跑 |
| 远程 fallback 产生 Stepfun 流量 | 仅极端兜底，正常演示全本地，远程几乎不调 |

**回退兜底**：所有本地路径由 `LOCAL_*` 环境变量门控。不设 → 完全等同预赛版（纯远程 + RAG 随 `EMBEDDING_BASE_URL`）。**最坏情况 = 现有预赛版本，零退化**。

---

## 13. 与 NVIDIA Agent Toolkit 对齐（路演加分）

| NVIDIA Agent Toolkit 层 | ReproForge 对应（本设计强化） |
|---|---|
| System of Models | 双轨 + fallback：本地 vLLM（文本 qwen3.6 + VL Qwen2.5-VL + bge embedding）为主，远程 stepfun 加固；统一 OpenAI 兼容 |
| Harness | LangGraph StateGraph（vision→evidence→reproduction→recall→investigator→regression），对齐官方 AI-Q Blueprint |
| Secure Runtime + Skills | Playwright 沙箱 + ripgrep/tree-sitter + faster-whisper；bge/vLLM 本地算力 |

> 路演话术：三服务全本地（体现 DGX Spark 全栈）+ 远程 fallback（体现工程健壮性 / 高可用），双卖点。

---

## 14. 实施顺序（writing-plans 详化）

1. **代码层**（本地，先做，不依赖服务器）：config.py 双轨拆分 → client.py fallback → store.py RemoteEF → 测试（test_client/test_config/test_store 改）→ 全 mock 跑绿
2. **服务器层**（SSH spark-71）：下 2 模型 → 起 3 服务 → 健康检查
3. **端到端验证**（本地经隧道）：smoke_vl 本地看图 → smoke_rag 本地 bge → smoke_fallback 兜底 → UI 全流程
4. 文档更新：`架构与部署.md` / `项目状态.md` / `Demo拍摄操作指南.md` 起动命令

每步可独立验证、独立回退。
