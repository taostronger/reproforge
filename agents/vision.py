"""agents/vision.py — VL 视觉 agent（看 Bug 截图提 expected/actual）

前置节点（evidence 前）：截图 + 口述 → step-3.7 多模态 → VisualFinding。
无截图 / 调用失败 → 返回空 finding（used=False），evidence 照旧口述驱动（降级）。
"""
import base64
import mimetypes
from dataclasses import dataclass

from llm.client import chat_vision


@dataclass
class VisualFinding:
    expected: str = ""
    actual: str = ""
    page_description: str = ""   # VL 对页面客观状态的描述
    confidence: float = 0.0      # 0-1，VL 自评
    needs_confirm: bool = False
    used: bool = False           # 是否真的用了视觉（无图/失败为 False）


_VL_PROMPT = """你是测试工程师。这是一张 Bug 截图，测试员口述：{narration}
请看图提取：预期值、实际值（页面实际显示的内容）、页面状态描述、置信度(0-1)。
只输出 JSON：{{"expected":"...","actual":"...","page_description":"...","confidence":0.0}}
若图里看不清关键信息，confidence 给低分。"""


def _to_data_uri(screenshot):
    """本地文件 → base64 data URI；已是 http/https/data 则原样返回（远程 API 访问不了本地 file://）。"""
    if screenshot.startswith(("http://", "https://", "data:")):
        return screenshot
    with open(screenshot, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    mime = mimetypes.guess_type(screenshot)[0] or "image/png"
    return f"data:{mime};base64,{b64}"


def analyze_screenshot(screenshot, narration):
    """看截图 + 口述 → VisualFinding。

    screenshot: 图片路径（本地）/ URL / None。
    narration: 测试员口述文本。
    无截图 / 任何调用失败 → 返回空 VisualFinding（used=False，evidence 照旧）。
    """
    if not screenshot:
        return VisualFinding()
    try:
        image_data_uri = _to_data_uri(screenshot)
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": _VL_PROMPT.format(narration=narration or "")},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        }]
        result = chat_vision(messages) or {}
        conf = float(result.get("confidence", 0.0) or 0.0)
        return VisualFinding(
            expected=str(result.get("expected", "")).strip(),
            actual=str(result.get("actual", "")).strip(),
            page_description=str(result.get("page_description", "")).strip(),
            confidence=conf,
            needs_confirm=conf < 0.6,
            used=True,
        )
    except Exception:
        return VisualFinding()
