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
    """多模态调用（content 可含 image_url，本地 Qwen2.5-VL 优先 + 远程 step-3.7 fallback）。

    为何 VL 用专用 Qwen2.5-VL 而非文本实例 qwen3.6：qwen3.6 虽是多模态（Qwen3.5 MoE，
    config.json 的 vision_config=True，实测能看图），但它是 reasoning 模型，输出大段
    推理、不遵循「只输出 JSON」指令；而 chat_vision 靠 re.search 提 JSON——故 VL 用
    instruction-tuned 的 Qwen2.5-VL，不用 qwen3.6 兼任（合并会导致 vision 降级）。
    """
    content = _chat_with_fallback(
        messages, get_local_vl_config(), get_remote_vl_config(),
        0.1, _VL_LOCAL_TIMEOUT, model=model)
    match = re.search(r'\{.*\}', content, re.S)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in vision response")
