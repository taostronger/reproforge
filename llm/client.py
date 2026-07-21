import json
import re
from unittest.mock import patch
from openai import OpenAI
from config import get_model_config

_client = None

def _get_client():
    global _client
    if _client is None:
        config = get_model_config()
        _client = OpenAI(base_url=config.base_url, api_key=config.api_key)
    return _client

def chat(messages, model=None, temperature=0.3):
    client = _get_client()
    cfg = get_model_config()
    resp = client.chat.completions.create(
        model=model or cfg.model, messages=messages, temperature=temperature,
    )
    content = resp.choices[0].message.content
    # 剥 reasoning thinking（保留思考质量，提取正文/JSON 时剥干净）
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()
    if '</think>' in content:          # vLLM 可能剥了 <think> 但留 </think> 及之前的思考
        content = content.split('</think>')[-1].strip()
    return content

def chat_json(messages, model=None):
    content = chat(messages, model=model, temperature=0.1)
    match = re.search(r'\{.*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")


def chat_vision(messages, model=None):
    """多模态调用（content 可含 image_url），固定走 VL 配置（远程 step-3.7 多模态，不受 PROFILE 影响）。

    本地 qwen3.6 不支持图像，故 VL 始终远程 step-3.7（本地 VL 留决赛 Qwen2.5-VL）。
    """
    from config import get_vl_model_config
    vl = get_vl_model_config()
    client = OpenAI(base_url=vl.base_url, api_key=vl.api_key)
    resp = client.chat.completions.create(
        model=model or vl.model, messages=messages, temperature=0.1,
    )
    content = resp.choices[0].message.content
    match = re.search(r'\{.*\}', content, re.S)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON in vision response")
