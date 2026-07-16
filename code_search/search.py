"""code_search/search.py — ripgrep + tree-sitter 代码检索（plan Task 2.5）

按查询词（组件名/路由/API/testid/错误文本）检索，
tree-sitter 提取命中所在函数/组件名作上下文，按命中数排序。纯确定性，不依赖 LLM。

检索引擎双模式：优先 ripgrep（subprocess，快；spark-71/Linux 有），
不可用时降级纯 Python 遍历（Windows 开发机兜底）。接口一致。
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_typescript as _tst
from tree_sitter import Language, Parser


@dataclass
class FileHit:
    path: str
    snippet: str = ""       # 命中行（最多3条）
    score: float = 0.0      # 命中数
    matches: int = 0
    context: str = ""       # 命中所处函数/组件名（tree-sitter 提取，best-effort）


# ---- tree-sitter 上下文提取 ----
_TSX_PARSER = None


def _get_tsx_parser():
    global _TSX_PARSER
    if _TSX_PARSER is None:
        _TSX_PARSER = Parser(Language(_tst.language_tsx()))
    return _TSX_PARSER


def _collect_scopes(node, acc):
    """递归收集函数/方法/类/变量声明 (name, start_line, end_line)；行号 0-based。"""
    if node.type in ("function_declaration", "method_definition", "class_declaration"):
        nm = node.child_by_field_name("name")
        acc.append((nm.text.decode() if nm else "?", node.start_point[0], node.end_point[0]))
    elif node.type == "variable_declarator":
        nm = node.child_by_field_name("name")
        acc.append((nm.text.decode() if nm else "?", node.start_point[0], node.end_point[0]))
    for c in node.children:
        _collect_scopes(c, acc)


def _enclosing_context(file_path, line_numbers):
    """命中行所在的最近函数/组件名（best-effort；非 TS/JS 或解析失败返回 ''）。"""
    try:
        p = Path(file_path)
        if not p.exists() or p.suffix not in (".tsx", ".ts", ".jsx", ".js"):
            return ""
        tree = _get_tsx_parser().parse(p.read_bytes())
        scopes = []
        _collect_scopes(tree.root_node, scopes)
        names = set()
        for ln in line_numbers:
            best, best_size = None, None
            for name, s, e in scopes:
                if s + 1 <= ln <= e + 1:  # tree-sitter 0-based → 1-based
                    size = e - s
                    if best_size is None or size < best_size:
                        best, best_size = name, size
            if best:
                names.add(best)
        return ",".join(sorted(names))
    except Exception:
        return ""


# ---- 检索引擎：ripgrep 优先，降级纯 Python ----
_IGNORED_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv",
                 "test-results", "playwright-report", ".playwright", "blob-report", ".nyc_output"}
_CODE_EXT = (".tsx", ".ts", ".jsx", ".js", ".py", ".json", ".css", ".html", ".md", ".vue", ".java", ".go", ".rs")


def _py_matches(query, repo):
    """纯 Python 子串检索（大小写不敏感）。rg 不可用时的兜底。"""
    pat = re.compile(re.escape(query), re.IGNORECASE)
    out = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        for fn in files:
            if not fn.endswith(_CODE_EXT):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pat.search(line):
                            out.append({"path": fp, "line": i, "text": line.rstrip()})
            except OSError:
                continue
    return out


def _matches(query, repo):
    """优先 ripgrep（快），不可用或无输出时降级纯 Python 遍历。"""
    cmd = ["rg", "-i", "-n", "--no-heading", "--json", query, str(repo)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.stdout:
            out = []
            for line in proc.stdout.splitlines():
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "match":
                    continue
                d = obj.get("data", {})
                out.append({
                    "path": d.get("path", {}).get("text", ""),
                    "line": d.get("line_number", 0),
                    "text": d.get("lines", {}).get("text", "").rstrip(),
                })
            if out:
                return out
    except (FileNotFoundError, OSError):
        pass
    return _py_matches(query, repo)


def search(query_terms, repo_path, top_n=5):
    """按查询词检索 repo_path，返回按命中数降序的 FileHit 列表（最多 top_n）。"""
    repo = Path(repo_path).resolve()
    terms = [query_terms] if isinstance(query_terms, str) else list(query_terms)
    agg = {}
    for q in terms:
        for h in _matches(q, repo):
            a = agg.setdefault(h["path"], {"matches": 0, "snippets": [], "lines": []})
            a["matches"] += 1
            a["snippets"].append(f"L{h['line']}: {h['text'].strip()}")
            a["lines"].append(h["line"])
    hits = [
        FileHit(
            path=p,
            snippet="\n".join(a["snippets"][:3]),
            score=float(a["matches"]),
            matches=a["matches"],
            context=_enclosing_context(p, a["lines"]),
        )
        for p, a in agg.items()
    ]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_n]
