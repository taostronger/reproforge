"""Phase A 命门验证（迭代版）：生成 → pytest → 反馈错误 → 重新生成 → 重跑，最多 N 轮。
单次生成不够（Stepfun baseline 只 1/2），命门真验证是"自主迭代修复"能力。
用法：PROFILE=local python spike/phaseA_codegen.py  (本地 qwen)
      python spike/phaseA_codegen.py                  (默认 Stepfun)
环境变量：PHASEA_MAX_ROUNDS（默认 3）
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from config import get_model_config

load_dotenv(ROOT / ".env")
_cfg = get_model_config()
client = OpenAI(base_url=_cfg.base_url, api_key=_cfg.api_key)
MODEL = _cfg.model
MAX_ROUNDS = int(os.getenv("PHASEA_MAX_ROUNDS", "3"))

SPEC = """你是资深 Python 后端工程师，在 ReproForge 项目里实现模型抽象层（plan Task 1.2）。

项目已有 config.py（不要重写，直接 import 用）：
```python
from dataclasses import dataclass

@dataclass
class ModelConfig:
    base_url: str
    model: str
    api_key: str

def get_model_config() -> ModelConfig:
    ...  # 返回 ModelConfig(base_url, model, api_key)
```

请实现 llm/client.py：
- 用 openai 包的 OpenAI 客户端
- 模块级全局 _client = None
- _get_client(): 惰性创建 OpenAI(base_url, api_key)（从 config.get_model_config() 取），复用 _client
- chat(messages, model=None, temperature=0.3) -> str: 调 _get_client().chat.completions.create(model=model or 配置model, messages=messages, temperature=temperature)，返回 resp.choices[0].message.content
- chat_json(messages, model=None) -> dict: 调 chat(messages, model=model, temperature=0.1)，从返回文本里提取首个 JSON 对象（可能被 ```json 包裹或前后有文字，用正则提取 {.*}），json.loads 返回 dict

⚠️ 测试注意：tests 用 unittest.mock.patch("llm.client.OpenAI") 替换 OpenAI。全局 _client 缓存会导致测试间 mock 污染——确保每次 mock 生效（例如 _get_client 在测试隔离下能拿到新 mock，或在 chat 里不缓存导致问题）。最稳妥：_get_client 内 `global _client; if _client is None: _client = OpenAI(...)`，但测试可能需要重置——你决定实现方式，务必让两个测试都过。

并写 tests/test_llm_client.py（pytest + unittest.mock）：
- test_chat_returns_content: patch("llm.client.OpenAI")，让返回 client.chat.completions.create 返回 MagicMock(choices=[MagicMock(message=MagicMock(content="hello"))])，断言 chat([{"role":"user","content":"hi"}]) == "hello"
- test_chat_json_parses_json: patch("llm.client.OpenAI")，返回 content='{"a":1}'，断言 chat_json([{"role":"user","content":"x"}]) == {"a":1}
- 注意两个测试独立的 mock 隔离（必要时在测试里重置 llm.client 的全局 _client）

严格按格式输出两个文件，不要解释：
===FILE: llm/client.py===
```python
<完整代码>
```
===FILE: tests/test_llm_client.py===
```python
<完整代码>
```"""


def llm(prompt):
    r = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.2,
    )
    return r.choices[0].message.content


def parse_and_write(raw):
    files = {}
    for m in re.finditer(r"===FILE:\s*([^=\n]+?)\s*===\s*```(?:python)?\n(.*?)```", raw, re.S):
        files[m.group(1).strip()] = m.group(2)
    for path, code in files.items():
        full = ROOT / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(code, encoding="utf-8")
    return files


def run_pytest():
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_llm_client.py", "-v"],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def main():
    print(f"模型={MODEL}  PROFILE={os.getenv('PROFILE', '(stepfun默认)')}  最大轮数={MAX_ROUNDS}")
    prompt = SPEC
    for rnd in range(1, MAX_ROUNDS + 1):
        print(f"\n===== Round {rnd} 生成 =====")
        raw = llm(prompt)
        print(raw[:200])
        files = parse_and_write(raw)
        if not files:
            print("PARSE_FAIL: 未按格式输出")
            prompt = SPEC + "\n\n上次未按 ===FILE: 路径=== 格式输出，请严格按格式。"
            continue
        for p in files:
            print(f"WROTE {p} ({len(files[p])} chars)")
        r = run_pytest()
        print(r.stdout[-700:])
        if r.returncode == 0:
            print(f"\n✅ PASS at round {rnd} （{MODEL}）")
            return
        last_code = files.get("llm/client.py", "")
        err = (r.stdout + r.stderr)[-1500:]
        prompt = SPEC + (
            f"\n\n上一轮你生成的 llm/client.py：\n```python\n{last_code}\n```\n"
            f"运行 pytest 失败：\n{err}\n请定位并修复 bug，重新严格输出两个完整文件（===FILE: 路径=== 格式）。"
        )
    print(f"\n❌ 未在 {MAX_ROUNDS} 轮内通过（{MODEL}）")


if __name__ == "__main__":
    main()
