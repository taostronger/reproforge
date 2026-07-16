"""agents/code_investigator.py — Agent3 代码调查（plan Task 2.6）

从 Bug 时间线提取查询词 → code_search 检索候选文件 → LLM 打分排序给理由 → Top3。
不宣称根因，只给可疑文件排序（诚实边界）。
"""
from dataclasses import dataclass, field
from pathlib import Path

from llm.client import chat_json
from code_search.search import search


@dataclass
class FileScore:
    path: str
    score: float = 0.0
    reason: str = ""
    snippet: str = ""
    context: str = ""


@dataclass
class TopFiles:
    files: list = field(default_factory=list)
    query_terms: list = field(default_factory=list)


_RANK_PROMPT = """你是资深前端工程师。测试员报告了一个 Bug，下面是代码检索命中的候选文件。
Bug：预期 {expected}，实际 {actual}
可疑操作：{actions}

候选文件（按命中数排序）：
{candidates}

请对每个候选文件打分（0-1，越高越可疑）并给一句话理由。只输出 JSON：
{{"scores": [{{"score": 0.9, "reason": "一句话理由"}}, ...]}}
scores 数组顺序与上面候选文件顺序一一对应。"""


def _useful(term):
    """有区分度的词：长度≥3 且非纯数字（排除 "2"/"160" 等噪声）。"""
    t = str(term)
    return len(t) >= 3 and not t.isdigit()


def _extract_query_terms(timeline, console_errors):
    """从 timeline/console 提检索词：testid、有区分度的值、console 文本。
    纯数字（如 qty 值、expected 金额）噪声大，不纳入检索；expected/actual 在 LLM 打分阶段仍用。"""
    terms = []
    for e in timeline.events:
        if getattr(e, "target", None) and _useful(e.target):
            terms.append(str(e.target))
        v = getattr(e, "value", None)
        if v and _useful(v):
            terms.append(str(v))
    for err in (console_errors or []):
        if isinstance(err, str) and _useful(err):
            terms.append(err)
    seen, uniq = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def investigate(timeline, console_errors, repo_path, top_n=3):
    """检索候选文件 → LLM 打分排序 → TopFiles（不宣称根因，只排序）。"""
    terms = _extract_query_terms(timeline, console_errors)
    hits = search(terms, repo_path, top_n=10)
    if not hits:
        return TopFiles(files=[], query_terms=terms)
    actions_desc = ", ".join(f"{e.action} {e.target}".strip() for e in timeline.events)
    lines = []
    for i, h in enumerate(hits):
        flat = " ".join(h.snippet.split())
        lines.append(f"{i}. {Path(h.path).name}（命中{h.matches}次，函数: {h.context or '?'}）\n   {flat}")
    candidates_desc = "\n".join(lines)
    prompt = _RANK_PROMPT.format(
        expected=timeline.expected, actual=timeline.actual,
        actions=actions_desc, candidates=candidates_desc,
    )
    try:
        result = chat_json([{"role": "user", "content": prompt}]) or {}
    except Exception:
        result = {}
    scores = result.get("scores") or []
    files = []
    for i, h in enumerate(hits):
        s = scores[i] if i < len(scores) and isinstance(scores[i], dict) else {}
        try:
            sc = float(s.get("score", h.score))
        except (TypeError, ValueError):
            sc = h.score
        files.append(FileScore(
            path=h.path, snippet=h.snippet, context=h.context,
            score=sc, reason=str(s.get("reason", "")),
        ))
    files.sort(key=lambda f: f.score, reverse=True)
    return TopFiles(files=files[:top_n], query_terms=terms)
