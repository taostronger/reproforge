# spark-71 bge 迁移 + VL 本地双轨 + 远程 fallback 加固 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ReproForge 的 RAG embedding 与 VL 视觉下沉到 spark-71 本地算力（三服务），并以远程 Stepfun API 作极端 fallback，实现「全本地为主 + 远程加固」。

**Architecture:** spark-71 跑三服务——文本 vLLM(:8000/util0.45) + VL vLLM Qwen2.5-VL(:8001/util0.4) + bge embedding FastAPI(:8002/CPU)，峰值显存 ~111GB。`config.py` 拆本地/远程两组配置；`llm/client.py` 做「本地优先 + 远程兜底」；`memory/store.py` 改 `RemoteEmbeddingFunction` 调远程 bge。本地经 SSH 隧道访问三端口。

**Tech Stack:** Python 3.12 · vLLM 0.23.1rc1（GB10，DeepGEMM=0）· FastAPI + sentence-transformers（bge）· chromadb · openai SDK · pytest。

**Spec:** `docs/superpowers/specs/2026-07-22-spark71-bge-vl-migration-design.md`

---

## ⚠️ 执行前置

1. **当前仓库处于 detached HEAD**——执行 Task 1 前先 `git checkout -b feat/spark71-bge-vl` 切到分支，避免 commit 丢失。
2. **commit 时机遵循队长约定**（CLAUDE.md：commit 需用户确认）。本计划每个 Task 末尾的 commit step 是建议节奏，实际 commit 前请示队长；不 commit 也可继续下一 Task。
3. **工作目录**：所有本地命令在 `项目代码/reproforge_spike/` 下执行。测试用 `pytest`。
4. **spark-71 SSH**：`ssh -p 6071 Developer@106.13.186.155`（密码见 `ssh信息/spark-71-连接指南.md`）。⚠️ 流量计费——模型全程服务器内 `huggingface-cli download` 走 hf-mirror，**严禁 scp 大文件**；脚本/代码等小文件可 scp。

---

## 文件结构

**本地新建：**
- `deploy/spark71/bge_server.py` — bge embedding FastAPI 服务（部署到 spark-71 `~/reproforge_serve/`）
- `deploy/spark71/download_models.sh` — 下 Qwen2.5-VL + bge（hf-mirror）
- `deploy/spark71/serve_text_vllm.sh` — 文本 vLLM 启动（util 0.45）
- `deploy/spark71/serve_vl_vllm.sh` — VL vLLM 启动（util 0.4）
- `deploy/spark71/serve_bge.sh` — bge 服务启动
- `deploy/spark71/start_all.sh` — 三服务编排 + 健康检查
- `scripts/tunnel.sh` — 本地三端口 SSH 隧道
- `tests/test_client.py` — fallback 逻辑测试
- `tests/test_config.py` — config 拆分测试
- `spike/smoke_fallback.py` — fallback 端到端冒烟

**本地修改：**
- `config.py` — 加 `get_local/remote_model_config`、`get_local/remote_vl_config`，保留旧函数
- `llm/client.py` — 加 `_call`/`_chat_with_fallback`，改造 `chat`/`chat_json`/`chat_vision`
- `memory/store.py` — `RemoteEmbeddingFunction` + `MemoryStore.__init__` 改远程 EF
- `tests/test_store.py` — mock 目标从 `SentenceTransformerEmbeddingFunction` 改 `RemoteEmbeddingFunction`
- `spike/smoke_rag.py` / `spike/smoke_vl.py` — 适配远程 embedding / 本地 VL
- `.env.example`（若无则新建）— 追加 `LOCAL_*` / `EMBEDDING_BASE_URL`
- `docs/架构与部署.md` / `docs/项目状态.md` / `docs/Demo拍摄操作指南.md` — 更新部署/启动命令

---

## 阶段一：代码层（不依赖服务器，TDD）

### Task 1: config.py 双轨拆分

**Files:**
- Modify: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败测试** `tests/test_config.py`

```python
"""config 双轨拆分测试：本地/远程配置的 None/返回逻辑。"""
from config import (ModelConfig, get_local_model_config, get_remote_model_config,
                    get_local_vl_config, get_remote_vl_config, get_model_config)


def test_get_local_model_config_no_env_returns_none(monkeypatch):
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    assert get_local_model_config() is None


def test_get_local_model_config_with_env(monkeypatch):
    monkeypatch.setenv("LOCAL_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LOCAL_MODEL", "/models/qwen36")
    monkeypatch.setenv("LOCAL_API_KEY", "vllm")
    cfg = get_local_model_config()
    assert cfg is not None
    assert cfg.base_url == "http://localhost:8000/v1"
    assert cfg.model == "/models/qwen36"
    assert cfg.is_local is True


def test_get_remote_model_config(monkeypatch):
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_remote_model_config()
    assert "stepfun" in cfg.base_url
    assert cfg.model == "step-3.7-flash"
    assert cfg.is_local is False


def test_get_local_vl_config_no_env_returns_none(monkeypatch):
    monkeypatch.delenv("LOCAL_VL_BASE_URL", raising=False)
    assert get_local_vl_config() is None


def test_get_local_vl_config_with_env(monkeypatch):
    monkeypatch.setenv("LOCAL_VL_BASE_URL", "http://localhost:8001/v1")
    monkeypatch.setenv("LOCAL_VL_MODEL", "Qwen2.5-VL-7B-Instruct")
    cfg = get_local_vl_config()
    assert cfg.base_url == "http://localhost:8001/v1"
    assert cfg.is_local is True


def test_get_remote_vl_config(monkeypatch):
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_remote_vl_config()
    assert "stepfun" in cfg.base_url
    assert cfg.is_local is False


def test_get_model_config_no_local_falls_back_to_remote(monkeypatch):
    """无 LOCAL_BASE_URL → get_model_config 返回远程（向后兼容 eval/compare.py）。"""
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_model_config()
    assert "stepfun" in cfg.base_url
```

- [ ] **Step 2: 验证失败** — `pytest tests/test_config.py -v` → FAIL（`ImportError: cannot import name 'get_local_model_config'`）

- [ ] **Step 3: 实现** — 用以下完整内容替换 `config.py`：

```python
"""ReproForge 双轨模型配置。

本地优先 + 远程 fallback：get_local_*_config 返回本地配置（无 LOCAL_* env 则 None），
get_remote_*_config 返回 Stepfun 远程。旧函数 get_model_config/get_vl_model_config 保留
（返回"主配置"= 本地 or 远程），向后兼容 eval/compare.py。
"""
import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    base_url: str
    model: str
    api_key: str
    is_local: bool = False


# —— 文本 ——
def get_local_model_config() -> ModelConfig | None:
    """本地文本 vLLM（spark-71 :8000）。无 LOCAL_BASE_URL → None（纯远程模式）。"""
    base = os.getenv("LOCAL_BASE_URL")
    if not base:
        return None
    return ModelConfig(
        base_url=base,
        model=os.getenv("LOCAL_MODEL", "qwen2.5-coder:7b"),
        api_key=os.getenv("LOCAL_API_KEY", "ollama"),
        is_local=True,
    )


def get_remote_model_config() -> ModelConfig:
    """远程 Stepfun step-3.7。"""
    return ModelConfig(
        base_url="https://api.stepfun.com/step_plan/v1",
        model=os.getenv("STEPFUN_MODEL", "step-3.7-flash"),
        api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
    )


# —— VL ——
def get_local_vl_config() -> ModelConfig | None:
    """本地 VL vLLM Qwen2.5-VL（spark-71 :8001）。无 LOCAL_VL_BASE_URL → None。"""
    base = os.getenv("LOCAL_VL_BASE_URL")
    if not base:
        return None
    return ModelConfig(
        base_url=base,
        model=os.getenv("LOCAL_VL_MODEL", "Qwen2.5-VL-7B-Instruct"),
        api_key=os.getenv("LOCAL_VL_API_KEY", "vllm"),
        is_local=True,
    )


def get_remote_vl_config() -> ModelConfig:
    """远程 Stepfun step-3.7 多模态。"""
    return ModelConfig(
        base_url="https://api.stepfun.com/step_plan/v1",
        model=os.getenv("VL_MODEL", "step-3.7-flash"),
        api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
    )


# —— 向后兼容（eval/compare.py 等旧调用）——
def get_model_config() -> ModelConfig:
    """主文本配置：本地优先，无则远程。"""
    return get_local_model_config() or get_remote_model_config()


def get_vl_model_config() -> ModelConfig:
    """主 VL 配置：本地优先，无则远程。"""
    return get_local_vl_config() or get_remote_vl_config()
```

- [ ] **Step 4: 验证通过** — `pytest tests/test_config.py -v` → 7 passed

- [ ] **Step 5: 回归** — `pytest tests/ -v -k "not smoke"` → 现有测试不应因 config 改动而破（get_model_config 行为兼容）。若 `test_llm_client.py` 等依赖旧 `_client` 单例，下一 Task 一起修。

- [ ] **Step 6: commit（如队长同意）**
```bash
git add config.py tests/test_config.py
git commit -m "feat(config): split local/remote model configs for fallback"
```

---

### Task 2: llm/client.py 本地优先 + 远程 fallback

**Files:**
- Modify: `llm/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: 写失败测试** `tests/test_client.py`

```python
"""client fallback 测试：本地优先，失败降级远程，都失败 raise。

全 mock _call（不触真实 openai/网络），验证 fallback 编排逻辑。
"""
import httpx
import pytest
from unittest.mock import patch, MagicMock


def _cfg(url, local=False):
    return MagicMock(base_url=url, model="m", api_key="k", is_local=local)


def test_chat_local_success_does_not_touch_remote():
    """本地成功 → _call 只调 1 次，参数是 local cfg。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", return_value="本地结果") as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "本地结果"
        assert mock_call.call_count == 1
        assert mock_call.call_args_list[0].args[0] is local


def test_chat_local_connection_error_falls_back_to_remote():
    """本地 httpx.ConnectError → fallback 远程，_call 调 2 次（local→remote）。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call",
               side_effect=[httpx.ConnectError("no local"), "远程结果"]) as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"
        assert mock_call.call_count == 2
        assert mock_call.call_args_list[1].args[0] is remote


def test_chat_local_timeout_falls_back_to_remote():
    """本地 httpx.TimeoutException → fallback 远程。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call",
               side_effect=[httpx.TimeoutException("slow"), "远程结果"]):
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"


def test_chat_no_local_goes_straight_to_remote():
    """无本地配置（None）→ 直接远程，_call 只 1 次，参数是 remote。"""
    remote = _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=None), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", return_value="远程结果") as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"
        assert mock_call.call_count == 1
        assert mock_call.call_args_list[0].args[0] is remote


def test_chat_both_fail_raises():
    """本地+远程都失败 → 不吞异常，raise（业务层降级）。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", side_effect=httpx.ConnectError("all dead")):
        from llm.client import chat
        with pytest.raises(httpx.ConnectError):
            chat([{"role": "user", "content": "hi"}])


def test_chat_vision_uses_vl_configs():
    """chat_vision 走 VL 的 local/remote 配置。"""
    local, remote = _cfg("http://vl-local", True), _cfg("http://vl-remote")
    with patch("llm.client.get_local_vl_config", return_value=local), \
         patch("llm.client.get_remote_vl_config", return_value=remote), \
         patch("llm.client._call", return_value='{"expected":"x"}') as mock_call:
        from llm.client import chat_vision
        chat_vision([{"role": "user", "content": "..."}])
        assert mock_call.call_args_list[0].args[0] is local
```

- [ ] **Step 2: 验证失败** — `pytest tests/test_client.py -v` → FAIL（`ImportError: cannot import name '_call'`）

- [ ] **Step 3: 实现** — 用以下完整内容替换 `llm/client.py`：

```python
"""llm/client.py — 统一 LLM 调用（本地优先 + 远程 fallback）。

chat/chat_json：文本（本地 vLLM → 远程 stepfun）。
chat_vision：VL 多模态（本地 Qwen2.5-VL → 远程 step-3.7）。
仅对"服务不可用"类异常（连接/超时/5xx）降级；4xx/鉴权失败不降级（兜底无意义）。
"""
import json
import logging
import re

import httpx
from openai import (APIConnectionError, APITimeoutError, InternalServerError, OpenAI)

from config import (get_local_model_config, get_local_vl_config,
                    get_remote_model_config, get_remote_vl_config)

log = logging.getLogger("reproforge.llm")
if not log.handlers:
    logging.basicConfig(level=logging.INFO)

_LOCAL_TIMEOUT = 60      # 文本本地
_VL_LOCAL_TIMEOUT = 120  # VL 本地（图像慢）

# 触发 fallback 的异常（服务不可用类）
_FALLBACK_EXC = (APIConnectionError, APITimeoutError, InternalServerError,
                 httpx.ConnectError, httpx.TimeoutException)


def _call(cfg, messages, temperature, timeout, model=None):
    """单次调用。每次按 cfg 新建 client（fallback 需独立 client）。"""
    client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=timeout)
    resp = client.chat.completions.create(
        model=model or cfg.model, messages=messages, temperature=temperature,
    )
    content = resp.choices[0].message.content
    # 剥 reasoning thinking（本地 qwen3.6 输出带 <think>）
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()
    if '</think>' in content:
        content = content.split('</think>')[-1].strip()
    return content


def _chat_with_fallback(messages, local, remote, temperature, timeout, model=None):
    """本地优先；失败（_FALLBACK_EXC）→ fallback 远程；都失败 raise。"""
    if local is not None:
        try:
            return _call(local, messages, temperature, timeout, model)
        except _FALLBACK_EXC as e:
            log.warning("[fallback] 本地 %s 失败(%s) → 切远程", local.base_url, type(e).__name__)
    return _call(remote, messages, temperature, timeout, model)


def chat(messages, model=None, temperature=0.3):
    """文本对话（本地优先 + 远程 fallback）。"""
    return _chat_with_fallback(
        messages, get_local_model_config(), get_remote_model_config(),
        temperature, _LOCAL_TIMEOUT, model=model)


def chat_json(messages, model=None):
    """文本对话 + JSON 提取。"""
    content = chat(messages, model=model, temperature=0.1)
    match = re.search(r'\{.*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")


def chat_vision(messages, model=None):
    """多模态调用（content 可含 image_url，本地 Qwen2.5-VL 优先 + 远程 step-3.7 fallback）。"""
    content = _chat_with_fallback(
        messages, get_local_vl_config(), get_remote_vl_config(),
        0.1, _VL_LOCAL_TIMEOUT, model=model)
    match = re.search(r'\{.*\}', content, re.S)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in vision response")
```

- [ ] **Step 4: 验证通过** — `pytest tests/test_client.py -v` → 6 passed

- [ ] **Step 5: 回归现有 client 测试** — `pytest tests/test_llm_client.py -v`。若有用例依赖旧 `_client` 单例或 `from llm.client import _get_client`，需同步更新（见 Step 6）。

- [ ] **Step 6: 修 test_llm_client.py（若失败）** — 旧测试若 import `_get_client`/`_client`，改为 mock `_call` 或删除针对单例的断言。先读 `tests/test_llm_client.py` 确认其断言，按新接口（`_call`/`_chat_with_fallback`）调整 mock 目标。

- [ ] **Step 7: commit（如队长同意）**
```bash
git add llm/client.py tests/test_client.py tests/test_llm_client.py
git commit -m "feat(llm): local-first chat/chat_vision with remote fallback"
```

---

### Task 3: memory/store.py RemoteEmbeddingFunction

**Files:**
- Modify: `memory/store.py`
- Modify: `tests/test_store.py`

- [ ] **Step 1: 改写失败测试** — 用以下完整内容替换 `tests/test_store.py`：

```python
"""memory/store 测试：mock chromadb + RemoteEmbeddingFunction，验证 ingest/query/冷启动/降级。"""
from unittest.mock import patch, MagicMock

import pytest


def test_remote_embedding_function_posts_and_returns_vectors():
    """RemoteEF.__call__ → POST /v1/embeddings，解析返回向量列表。"""
    with patch("memory.store.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        from memory.store import RemoteEmbeddingFunction
        ef = RemoteEmbeddingFunction("http://bge:8002")
        out = ef(["文本1", "文本2"])
        assert out == [[0.1, 0.2], [0.3, 0.4]]
        body = mock_post.call_args.kwargs["json"]
        assert body["input"] == ["文本1", "文本2"]
        assert body["model"] == "bge-large-zh"
        assert mock_post.call_args.args[0] == "http://bge:8002/v1/embeddings"


def test_memory_store_init_requires_embedding_url(monkeypatch):
    """无 EMBEDDING_BASE_URL 且未传 embedding_url → RuntimeError（→ get_memory_store 降级 None）。"""
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    with patch("memory.store.chromadb.PersistentClient"):
        from memory.store import MemoryStore
        with pytest.raises(RuntimeError):
            MemoryStore(path="./tmp_nourl")


def test_memory_store_ingest_calls_add_with_expected_actual_suspected():
    """ingest_issue → col.add，文档含 expected/actual/suspected。"""
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        issue = MagicMock(expected="160", actual="80", suspected_files=["App.tsx"],
                          minimal_steps=["1 click x"], stable_rate="3/3")
        timeline = MagicMock(events=[MagicMock(target="qty-input")], expected="160", actual="80")
        ms.ingest_issue(issue, timeline, None)
        ms.col.add.assert_called_once()
        doc = ms.col.add.call_args.kwargs["documents"][0]
        assert "160" in doc and "80" in doc and "App.tsx" in doc
        assert ms.col.add.call_args.kwargs["ids"][0]


def test_query_similar_empty_collection_returns_empty():
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        ms.col.count.return_value = 0
        timeline = MagicMock(events=[], expected="160", actual="80")
        assert ms.query_similar(timeline, []) == []


def test_query_similar_returns_ranked_results():
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        ms.col.count.return_value = 2
        ms.col.query.return_value = {
            "documents": [["d1", "d2"]],
            "metadatas": [[{"expected": "160"}, {"expected": "99"}]],
            "distances": [[0.1, 0.5]],
        }
        timeline = MagicMock(events=[MagicMock(target="qty")], expected="160", actual="80")
        out = ms.query_similar(timeline, [], top_k=2)
        assert len(out) == 2
        assert out[0]["doc"] == "d1" and out[0]["distance"] == 0.1


def test_get_memory_store_off_returns_none(monkeypatch):
    monkeypatch.setenv("REPROFORGE_MEMORY", "off")
    from memory.store import get_memory_store
    assert get_memory_store() is None


def test_get_memory_store_init_failure_returns_none(monkeypatch):
    """无 EMBEDDING_BASE_URL → MemoryStore 抛 RuntimeError → get_memory_store 返回 None。"""
    monkeypatch.setenv("REPROFORGE_MEMORY", "on")
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    with patch("memory.store.chromadb.PersistentClient"):
        from memory.store import get_memory_store
        assert get_memory_store() is None
```

- [ ] **Step 2: 验证失败** — `pytest tests/test_store.py -v` → FAIL（`ImportError: cannot import name 'RemoteEmbeddingFunction'`）

- [ ] **Step 3: 实现** — 用以下完整内容替换 `memory/store.py`：

```python
"""memory/store.py — chromadb 持久化 + 远程 bge embedding（spark-71 服务）。

ingest_issue：Issue 入库；query_similar：检索相似历史 Bug。
无 EMBEDDING_BASE_URL / 服务不可用 / 空库 → 由上层 recall 降级（investigator 照旧）。

设计：embedding 算力下沉 spark-71（bge 服务），本地只留 chromadb 向量库 + requests。
演示机不再需要 torch/sentence-transformers。
"""
import os
import uuid

import chromadb
import requests


class RemoteEmbeddingFunction:
    """调远程 bge 服务的 /v1/embeddings（OpenAI 兼容），符合 chromadb EF 协议。"""

    def __init__(self, base_url, model="bge-large-zh", timeout=30):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    def __call__(self, input: list[str]) -> list[list[float]]:
        # chromadb 0.5+ 要求 __call__ 带 (input) -> Embeddings 类型注解
        resp = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": input, "model": self.model},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]


class MemoryStore:
    """本地持久化向量库（chromadb）+ 远程 embedding（spark-71 bge）。"""

    def __init__(self, path=None, embedding_url=None, embedding_model="bge-large-zh"):
        self.path = path or os.getenv("REPROFORGE_MEMORY_PATH", "./reproforge_memory")
        url = embedding_url or os.getenv("EMBEDDING_BASE_URL")
        if not url:
            raise RuntimeError("无 EMBEDDING_BASE_URL，远程 embedding 不可用")
        self.client = chromadb.PersistentClient(path=self.path)
        self.ef = RemoteEmbeddingFunction(url, embedding_model)
        self.col = self.client.get_or_create_collection("bug_issues", embedding_function=self.ef)

    def ingest_issue(self, issue, timeline, top_files):
        """Issue 入库。文档=expected+actual+可疑文件+testid；metadata 存复现细节。"""
        testids = " ".join(e.target for e in timeline.events if getattr(e, "target", None))
        doc = f"预期 {timeline.expected} 实际 {timeline.actual} "
        doc += " ".join(issue.suspected_files) + " " + testids
        self.col.add(
            documents=[doc],
            metadatas=[{
                "expected": timeline.expected or "",
                "actual": timeline.actual or "",
                "suspected": ",".join(issue.suspected_files),
                "minimal_steps": " | ".join(issue.minimal_steps),
                "stable_rate": issue.stable_rate or "",
            }],
            ids=[str(uuid.uuid4())],
        )

    def query_similar(self, timeline, actions, top_k=3):
        """检索相似历史 Bug。空库返回 []（冷启动）。"""
        if self.col.count() == 0:
            return []
        testids = " ".join(e.target for e in timeline.events if getattr(e, "target", None))
        query = f"预期 {timeline.expected} 实际 {timeline.actual} {testids}"
        res = self.col.query(query_texts=[query], n_results=top_k)
        return [{"doc": res["documents"][0][i], "metadata": res["metadatas"][0][i],
                 "distance": res["distances"][0][i]}
                for i in range(len(res["documents"][0]))]

    def list_all(self):
        """返回所有历史 Bug Issue（UI 展示用）。空库 → []。"""
        if self.col.count() == 0:
            return []
        data = self.col.get(include=["documents", "metadatas"])
        return [{"doc": data["documents"][i], **(data["metadatas"][i] or {})}
                for i in range(len(data["documents"]))]


def get_memory_store():
    """构造 MemoryStore；REPROFORGE_MEMORY=off 或初始化失败 → 返回 None（降级）。"""
    if os.getenv("REPROFORGE_MEMORY", "on").lower() == "off":
        return None
    try:
        return MemoryStore()
    except Exception:
        return None
```

- [ ] **Step 4: 验证通过** — `pytest tests/test_store.py -v` → 7 passed

- [ ] **Step 5: commit（如队长同意）**
```bash
git add memory/store.py tests/test_store.py
git commit -m "feat(memory): remote bge embedding via spark-71, drop local torch dep"
```

---

### Task 4: 冒烟脚本适配远程 embedding / 本地 VL

**Files:**
- Modify: `spike/smoke_rag.py`
- Modify: `spike/smoke_vl.py`
- Create: `spike/smoke_fallback.py`

- [ ] **Step 1: 改 smoke_rag.py** — 把第 15-18 行的 HF 镜像 env 替换为远程 embedding env。定位：

```python
# bge 下载复用 whisper 的 HF 镜像环境变量
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("REPROFORGE_MEMORY", "on")
```

替换为：

```python
# RAG embedding 走 spark-71 bge 服务（经隧道 :8002）
os.environ.setdefault("EMBEDDING_BASE_URL", "http://localhost:8002")
os.environ.setdefault("REPROFORGE_MEMORY", "on")
```

并把开头的提示文字（第 30 行附近 `print("(首次下 bge-large-zh ~1.3GB...")`）改为：

```python
print("(embedding 走 spark-71 bge 服务 http://localhost:8002，需先起服务 + 隧道)")
```

- [ ] **Step 2: 改 smoke_vl.py** — 在 `load_dotenv(...)` 之后、`from agents.vision import` 之前，插入说明性 env 默认值（VL 走本地 Qwen2.5-VL 需 .env 有 `LOCAL_VL_BASE_URL`；无则自动远程 step-3.7）：

```python
# VL：.env 设 LOCAL_VL_BASE_URL 走本地 Qwen2.5-VL（经隧道 :8001）；无则远程 step-3.7
```

（无需改逻辑——chat_vision 内部已自动 fallback。仅加注释说明。）

- [ ] **Step 3: 新增 smoke_fallback.py** — 验证 fallback：故意指向不存在的本地 VL，确认 chat_vision 降级远程成功。

```python
"""fallback 冒烟：故意把 LOCAL_VL_BASE_URL 指向无人监听的端口，
确认 chat_vision 自动降级到远程 step-3.7 并成功返回。

用法：python spike/smoke_fallback.py [截图路径]
看 used=True 即 fallback 链路通（本地挂 → 远程兜底成功）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 故意指向无人端口，逼本地 VL 失败 → 触发远程 fallback
os.environ["LOCAL_VL_BASE_URL"] = "http://localhost:9999/v1"
os.environ["LOCAL_VL_MODEL"] = "none"

from agents.vision import analyze_screenshot

screenshot = sys.argv[1] if len(sys.argv) > 1 else r"C:\计算机项目\hackthon0625\提交要求\提交.png"
narration = "这是黑客松提交要求截图，请识别要点"

print("=== fallback 冒烟：本地 VL 故意失败 → 远程兜底 ===")
print(f"LOCAL_VL_BASE_URL={os.environ['LOCAL_VL_BASE_URL']}（应连不上）")
vf = analyze_screenshot(screenshot, narration)
print(f"used={vf.used}  confidence={vf.confidence:.2f}")
if vf.used:
    print("[OK] 本地 VL 挂了，远程 fallback 成功 → 加固链路通")
else:
    print("[WARN] fallback 也失败（远程 step-3.7 也连不上/不支持图）")
```

- [ ] **Step 4: 手动验证 smoke_fallback（需 .env 有 STEPCONFIG_FUN_API_KEY）** — 远程 step-3.7 可达时：`python spike/smoke_fallback.py` → 预期 `used=True`（本地 9999 连不上，fallback 远程成功）。若远程也不可达，跳过（部署阶段再验）。

- [ ] **Step 5: commit（如队长同意）**
```bash
git add spike/smoke_rag.py spike/smoke_vl.py spike/smoke_fallback.py
git commit -m "test(spike): adapt smoke scripts to remote embedding + add fallback smoke"
```

---

### Task 5: 部署产物 + 隧道脚本 + .env.example

**Files:**
- Create: `deploy/spark71/bge_server.py`
- Create: `deploy/spark71/download_models.sh`
- Create: `deploy/spark71/serve_text_vllm.sh`
- Create: `deploy/spark71/serve_vl_vllm.sh`
- Create: `deploy/spark71/serve_bge.sh`
- Create: `deploy/spark71/start_all.sh`
- Create: `scripts/tunnel.sh`
- Create: `.env.example`

- [ ] **Step 1: bge_server.py** — `deploy/spark71/bge_server.py`

```python
"""bge embedding 服务（spark-71，CPU，OpenAI 兼容 /v1/embeddings）。

部署：scp 到 ~/reproforge_serve/bge_server.py，uvicorn 起 :8002。
依赖：sentence-transformers, fastapi, uvicorn（spark-71 comfyui-env 已有 torch）。
"""
from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODEL_PATH = "/home/Developer/models/bge-large-zh-v1.5"

app = FastAPI(title="ReproForge bge embedding")
_model = SentenceTransformer(MODEL_PATH, device="cpu")


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

- [ ] **Step 2: download_models.sh** — `deploy/spark71/download_models.sh`

```bash
#!/usr/bin/env bash
# 在 spark-71 执行：下 Qwen2.5-VL-7B + bge-large-zh（走 hf-mirror，避免流量费）
set -e
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1

echo "[1/2] 下载 Qwen2.5-VL-7B-Instruct (~15GB)..."
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct \
  --local-dir ~/models/Qwen2.5-VL-7B-Instruct

echo "[2/2] 下载 bge-large-zh-v1.5 (~1.3GB)..."
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir ~/models/bge-large-zh-v1.5

echo "完成：~/models/Qwen2.5-VL-7B-Instruct + ~/models/bge-large-zh-v1.5"
```

- [ ] **Step 3: serve_text_vllm.sh** — `deploy/spark71/serve_text_vllm.sh`

```bash
#!/usr/bin/env bash
# 文本 vLLM（spark-71 :8000，util 0.45，与 VL 共存腾显存）
# 复用现有镜像/模型，仅改 util 0.8→0.45；必须带 DeepGEMM=0
set -e
docker rm -f vllm-text 2>/dev/null || true
docker run -d --name vllm-text --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 \
  -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models \
  eugr/spark-vllm:latest \
  vllm serve /models/qwen36-35b-a3b --host 0.0.0.0 --port 8000 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.45 \
    --max-model-len 8192 --max-num-batched-tokens 4096 \
    --load-format fastsafetensors --kv-cache-dtype fp8 --enable-prefix-caching
echo "vllm-text 启动中（预热 2-3 分钟），日志：docker logs -f vllm-text"
```

- [ ] **Step 4: serve_vl_vllm.sh** — `deploy/spark71/serve_vl_vllm.sh`

```bash
#!/usr/bin/env bash
# VL vLLM（spark-71 :8001，util 0.4，Qwen2.5-VL-7B）
# 注意：--limit-mm-per-prompt 参数名按 vLLM 0.23.1rc1 实测，新版可能为 --limit-mm-per-request
set -e
docker rm -f vllm-vl 2>/dev/null || true
docker run -d --name vllm-vl --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 \
  -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models \
  eugr/spark-vllm:latest \
  vllm serve /models/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8001 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.4 \
    --max-model-len 8192 --limit-mm-per-prompt image=1 \
    --max-num-batched-tokens 4096 --enable-prefix-caching
echo "vllm-vl 启动中（预热 2-3 分钟），日志：docker logs -f vllm-vl"
```

- [ ] **Step 5: serve_bge.sh** — `deploy/spark71/serve_bge.sh`

```bash
#!/usr/bin/env bash
# bge embedding 服务（spark-71 :8002，CPU）
# 先 scp deploy/spark71/bge_server.py 到 ~/reproforge_serve/
set -e
mkdir -p ~/reproforge_serve
# 用 comfyui-env 的 python（有 torch+sentence-transformers）；若无则 pip 装
PYTHON=${PYTHON:-~/build_a_claw_workshop-bundle/comfyui-env/bin/python}
cd ~/reproforge_serve
nohup $PYTHON -m uvicorn bge_server:app --host 0.0.0.0 --port 8002 > bge.log 2>&1 &
echo "bge 启动 :8002（CPU），日志：~/reproforge_serve/bge.log"
```

- [ ] **Step 6: start_all.sh** — `deploy/spark71/start_all.sh`

```bash
#!/usr/bin/env bash
# 编排：下模型 → 起三服务 → 健康检查
set -e
cd "$(dirname "$0")"

echo "=== 0. 模型（已下则跳过）==="
[ -d ~/models/Qwen2.5-VL-7B-Instruct ] && [ -d ~/models/bge-large-zh-v1.5 ] || bash download_models.sh

echo "=== 1. 文本 vLLM :8000 ==="
bash serve_text_vllm.sh
echo "=== 2. VL vLLM :8001 ==="
bash serve_vl_vllm.sh
echo "=== 3. bge :8002 ==="
bash serve_bge.sh

echo "=== 等待预热（vLLM 各 2-3 分钟）==="
sleep 5
echo "健康检查（vLLM 未就绪属正常，稍后重试）："
for p in 8000 8001 8002; do
  echo -n "port $p: "
  curl -s --max-time 3 http://localhost:$p/v1/models && echo "" || echo "not ready"
done
```

- [ ] **Step 7: tunnel.sh** — `scripts/tunnel.sh`

```bash
#!/usr/bin/env bash
# 本地三端口 SSH 隧道 → spark-71（文本:8000 / VL:8001 / bge:8002）
# 前台运行，Ctrl-C 断开。密码见 ssh信息/spark-71-连接指南.md
exec ssh -p 6071 -N \
  -L 8000:localhost:8000 \
  -L 8001:localhost:8001 \
  -L 8002:localhost:8002 \
  -o ServerAliveInterval=30 \
  Developer@106.13.186.155
```

- [ ] **Step 8: .env.example** — `.env.example`（新建；真实 .env 含密钥勿提交）

```
# ReproForge 环境变量示例（复制为 .env 填真实值）

# —— 远程 Stepfun（fallback + 开发态主用）——
STEPCONFIG_FUN_API_KEY=your_stepfun_key_here

# —— 本地三服务（演示态；经 SSH 隧道，开发态留空=纯远程）——
# 文本 vLLM（spark-71 :8000）
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL=/models/qwen36-35b-a3b
LOCAL_API_KEY=vllm
# VL vLLM（spark-71 :8001）
LOCAL_VL_BASE_URL=http://localhost:8001/v1
LOCAL_VL_MODEL=/models/Qwen2.5-VL-7B-Instruct
LOCAL_VL_API_KEY=vllm
# bge embedding（spark-71 :8002）
EMBEDDING_BASE_URL=http://localhost:8002

# —— 功能开关（off 则降级，主流水线照跑）——
REPROFORGE_VL=on
REPROFORGE_MEMORY=on
REPROFORGE_MEMORY_PATH=./reproforge_memory
```

- [ ] **Step 9: 确认 .gitignore 含 .env** — 防密钥泄露（.env 含 Stepfun key）：

```bash
cd 项目代码/reproforge_spike
grep -qxF '.env' .gitignore 2>/dev/null || echo '.env' >> .gitignore
grep -qxF 'reproforge_memory/' .gitignore 2>/dev/null || echo 'reproforge_memory/' >> .gitignore
```

- [ ] **Step 10: commit（如队长同意）**
```bash
git add deploy/ scripts/tunnel.sh .env.example .gitignore
git commit -m "chore(deploy): spark-71 serve scripts + tunnel + env example"
```

---

## 阶段二：服务器部署（SSH spark-71，执行 + 健康检查）

> 以下 Task 在 spark-71 执行。先 `ssh -p 6071 Developer@106.13.186.155` 登录。
> ⚠️ 大文件（模型）全程 hf-mirror 下载，**不 scp**。脚本/代码小文件可 scp。

### Task 6: 传脚本 + 下模型

**Files:**
- Upload（scp 小文件）: `deploy/spark71/*` → `~/reproforge_serve/`

- [ ] **Step 1: scp 部署脚本到 spark-71**（本地 Git Bash 执行）

```bash
cd 项目代码/reproforge_spike
scp -P 6071 deploy/spark71/*.sh deploy/spark71/bge_server.py \
  Developer@106.13.186.155:~/reproforge_serve/
```

- [ ] **Step 2: 在 spark-71 赋权 + 下模型**

```bash
ssh -p 6071 Developer@106.13.186.155
cd ~/reproforge_serve && chmod +x *.sh
bash download_models.sh
```

- [ ] **Step 3: 验证模型就位** — 预期两个目录存在且非空：

```bash
ls -la ~/models/Qwen2.5-VL-7B-Instruct/ | head
ls -la ~/models/bge-large-zh-v1.5/ | head
```

Expected: 两目录各含 `config.json` + 权重文件（VL 有 `.safetensors`，bge 有 `pytorch_model.bin`/`model.safetensors`）。

---

### Task 7: 起文本 vLLM（util 0.45）+ 健康检查

- [ ] **Step 1: 停旧 vLLM（util 0.8 的）再起新的**（spark-71）

```bash
docker rm -f vllm vllm-text 2>/dev/null   # 清理旧容器（旧名 vllm 或 vllm-text）
cd ~/reproforge_serve && bash serve_text_vllm.sh
```

- [ ] **Step 2: 等 2-3 分钟看启动日志** — 预期看到 `Application startup complete` / `Uvicorn running on ...:8000`：

```bash
docker logs -f vllm-text
# 看到 "Started server process" / "Waiting for application startup" 完成后 Ctrl-C 退出日志
```

- [ ] **Step 3: 健康检查** — `curl -s http://localhost:8000/v1/models` → 预期返回 `{"data":[{"id":"/models/qwen36-35b-a3b"...}]}`。

- [ ] **Step 4: 验证推理** —

```bash
curl -s http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"/models/qwen36-35b-a3b","messages":[{"role":"user","content":"说OK"}],"max_tokens":10}' | head -c 300
```

Expected: `choices` 含非空 `message.content`。

- [ ] **Step 5: 验证显存** — `free -h` → 预期 `used` 约 +59GB（vLLM-text 占用）。记录 baseline。

> ⚠️ 若启动 ~40s 后 `docker ps -a` 显示 vllm-text 为 `Exited(1)`：日志应有 `NVCC compilation failed` → 确认带了 `-e VLLM_USE_DEEP_GEMM=0`（serve_text_vllm.sh 已带）。其他错误贴日志排查。

---

### Task 8: 起 VL vLLM（util 0.4）+ 健康检查

- [ ] **Step 1: 起 VL 实例**（spark-71，与文本共存）

```bash
cd ~/reproforge_serve && bash serve_vl_vllm.sh
```

- [ ] **Step 2: 等预热 + 看日志** — `docker logs -f vllm-vl`，预期 `Application startup complete`。

> ⚠️ 若报 `unrecognized arguments: --limit-mm-per-prompt`：改用新版参数名重起。执行：
> ```bash
> docker rm -f vllm-vl
> # 编辑 serve_vl_vllm.sh 把 --limit-mm-per-prompt image=1 改为 --limit-mm-per-request image=1
> nano ~/reproforge_serve/serve_vl_vllm.sh
> bash serve_vl_vllm.sh
> ```
> 同步改本地 `deploy/spark71/serve_vl_vllm.sh` 保持一致（之后 commit）。

- [ ] **Step 3: 健康检查** — `curl -s http://localhost:8001/v1/models` → 预期返回 Qwen2.5-VL id。

- [ ] **Step 4: 验证 VL 推理（带图）** — 用 spark-71 上一张图测（若无，跳过，本地冒烟阶段再测）：

```bash
# 准备一张测试图（用 ImageMagick 生成或 scp 一张小图）
curl -s http://localhost:8001/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model":"/models/Qwen2.5-VL-7B-Instruct",
  "messages":[{"role":"user","content":[
    {"type":"text","text":"这张图里有什么？只回5个字"},
    {"type":"image_url","image_url":{"url":"https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png"}}
  ]}],
  "max_tokens":20
}' | head -c 400
```

Expected: `choices[0].message.content` 非空（VL 看懂了图）。若图片 URL 不可达，换本地 base64 或本地冒烟验证。

- [ ] **Step 5: 验证双实例显存共存** — `free -h` → 预期 `used` 累计约 +107GB（text 59 + vl 48），**峰值 ≤ ~111GB，留 ≥ 8GB**。若逼近 119GB → 把文本 util 降到 0.4（`docker rm -f vllm-text` 后改 serve_text_vllm.sh 的 `0.45`→`0.4` 重起）。

---

### Task 9: 起 bge 服务 + 健康检查

- [ ] **Step 1: 起 bge 服务**（spark-71）

```bash
cd ~/reproforge_serve && bash serve_bge.sh
sleep 15   # 等模型加载（bge-large CPU 首次加载 ~10s）
```

- [ ] **Step 2: 健康检查** —

```bash
curl -s http://localhost:8002/v1/models
curl -s http://localhost:8002/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"input":["测试中文向量化"],"model":"bge-large-zh"}' | head -c 200
```

Expected: `/v1/models` 返回 `bge-large-zh`；`/v1/embeddings` 返回 `"embedding":[...]`（非空浮点数组）。

> ⚠️ 若 `ModuleNotFoundError: sentence_transformers`：`~/build_a_claw_workshop-bundle/comfyui-env/bin/pip install sentence-transformers fastapi uvicorn`，再 `PYTHON=.../comfyui-env/bin/python bash serve_bge.sh`。若 comfyui-env 无 fastapi，`pip install fastapi uvicorn`。

- [ ] **Step 3: 验证三服务同活** —

```bash
for p in 8000 8001 8002; do echo -n "port $p: "; curl -s --max-time 3 http://localhost:$p/v1/models >/dev/null && echo OK || echo FAIL; done
```

Expected: 三个都 `OK`。

---

## 阶段三：端到端验证（本地经隧道）

### Task 10: 隧道 + 本地 VL 冒烟

- [ ] **Step 1: 起隧道**（本地，新开一个 Git Bash 窗口，前台保持）

```bash
cd 项目代码/reproforge_spike && bash scripts/tunnel.sh
# 保持窗口开着；另开窗口继续
```

- [ ] **Step 2: 本地验证三端口可达**

```bash
for p in 8000 8001 8002; do echo -n "localhost:$p "; curl -s --max-time 3 http://localhost:$p/v1/models >/dev/null && echo OK || echo FAIL; done
```

Expected: 三个 `OK`。

- [ ] **Step 3: 本地 VL 冒烟（走本地 Qwen2.5-VL）** — `.env` 已设 `LOCAL_VL_BASE_URL`/`LOCAL_VL_MODEL`。

```bash
cd 项目代码/reproforge_spike
python spike/smoke_vl.py "C:\计算机项目\hackthon0625\提交要求\提交.png"
```

Expected: `used=True`，`page_description` 非空（本地 Qwen2.5-VL 看懂截图）。看日志应有「本地优先」无 fallback warning。

---

### Task 11: 本地 RAG 冒烟（远程 embedding）

- [ ] **Step 1: 本地 RAG 冒烟**（`.env` 已设 `EMBEDDING_BASE_URL=http://localhost:8002`）

```bash
cd 项目代码/reproforge_spike
python spike/smoke_rag.py
```

Expected: `recall: used=True` 命中 1 条（embedding 走 spark-71 bge，chromadb 本地检索成功）。看无 torch 本地下载（embedding 远程）。

> ⚠️ 若 `RuntimeError: 无 EMBEDDING_BASE_URL` → 确认 `.env` 有该变量且 `load_dotenv` 加载（smoke_rag.py 开头有 `load_dotenv`）。

---

### Task 12: fallback 冒烟 + UI 全流程

- [ ] **Step 1: fallback 冒烟**（本地，故意断本地 VL）

```bash
cd 项目代码/reproforge_spike
python spike/smoke_fallback.py "C:\计算机项目\hackthon0625\提交要求\提交.png"
```

Expected: `used=True`，日志有 `[fallback] 本地 http://localhost:9999/v1 失败(ConnectError) → 切远程`，远程 step-3.7 兜底成功。

- [ ] **Step 2: 手动验真实 fallback** — 在 spark-71 停 VL：`docker stop vllm-vl`，本地重跑 `smoke_vl.py` → 预期 `[fallback]` 日志 + 远程成功。恢复：`ssh -p 6071 Developer@106.13.186.155 'docker start vllm-vl'`。

- [ ] **Step 3: UI 全流程**（演示态：本地为主 + 远程 fallback）

```bash
cd 项目代码/reproforge_spike
# 确认 .env 含 LOCAL_* + EMBEDDING_BASE_URL + STEPCONFIG_FUN_API_KEY
python ui/app.py
```

按 `Demo拍摄操作指南.md` 跑 Bug1 复现 + 上传截图（VL）+ 看 Issue 输出 + 记忆库 ingest。预期：全本地（文本+VL+bge），日志无 fallback warning（说明三服务健康）。

- [ ] **Step 4: 回归全测试** —

```bash
cd 项目代码/reproforge_spike
pytest tests/ -v -k "not smoke"
```

Expected: 全绿（test_config / test_client / test_store / test_vision / test_llm_client / 其他）。

---

## 阶段四：文档更新

### Task 13: 更新部署/状态/演示文档

**Files:**
- Modify: `docs/架构与部署.md`
- Modify: `docs/项目状态.md`
- Modify: `docs/Demo拍摄操作指南.md`

- [ ] **Step 1: 架构与部署.md** — 第四节「部署架构」更新：
  - 三服务表（文本 :8000/util0.45 + VL :8001/util0.4 + bge :8002/CPU，峰值 ~111GB）
  - 调用模型小节改为「本地优先 + 远程 fallback」，贴 `_chat_with_fallback` 触发条件表
  - 把「vLLM 本地部署」的启动命令指向 `deploy/spark71/start_all.sh`
  - 第五节「运行时组件」VL/RAG 行改为本地（Qwen2.5-VL :8001 / bge :8002，远程作 fallback）

- [ ] **Step 2: 项目状态.md** — 更新：
  - 「待办」第 1、2 项标记 ✅ 完成（bge 挪 spark-71 / VL 本地双轨）
  - 「决赛」小节更新（三服务部署 + fallback 加固已就绪，剩自动截图/C-D 端到端）
  - 「本地服务」行加 :8001 VL / :8002 bge
  - 「双轨」行改为「本地为主 + 远程 fallback」

- [ ] **Step 3: Demo拍摄操作指南.md** — 启动命令更新为演示态三服务：
  - 先 spark-71 `bash ~/reproforge_serve/start_all.sh`
  - 本地 `bash scripts/tunnel.sh`（另窗口）
  - 本地 `python ui/app.py`（.env 含 LOCAL_* + EMBEDDING_BASE_URL）
  - 标注「全本地为主，远程 stepfun 自动兜底」

- [ ] **Step 4: commit（如队长同意）**
```bash
git add docs/架构与部署.md docs/项目状态.md docs/Demo拍摄操作指南.md
git commit -m "docs: spark-71 three-service deploy + local-first fallback architecture"
```

---

## 完成判据（Definition of Done）

- [ ] `pytest tests/ -v -k "not smoke"` 全绿（含新 test_config/test_client + 改造 test_store）
- [ ] spark-71 三服务同活（:8000 文本 / :8001 VL / :8002 bge），峰值显存 ≤ ~111GB
- [ ] 本地经隧道：smoke_vl 本地 Qwen2.5-VL 看图成功、smoke_rag 远程 embedding 成功、smoke_fallback 兜底成功
- [ ] UI 全流程（Bug1 复现 + VL + Issue）全本地跑通，日志无 fallback warning
- [ ] 文档三处更新，启动命令指向 start_all.sh + tunnel.sh
- [ ] 匿名自检（真名/私人称呼零容忍）：对全仓库检索队长真名与一切私人关系称呼，确认代码与对外文档无命中（敏感词不内联本文件，按 CLAUDE.md §10 执行）
