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
    resp = client.chat.completions.create(
        model=model or get_model_config().model,
        messages=messages,
        temperature=temperature
    )
    return resp.choices[0].message.content

def chat_json(messages, model=None):
    content = chat(messages, model=model, temperature=0.1)
    match = re.search(r'\{.*\}', content)
    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in response")
