"""RAG 冒烟：验证 bge-large-zh + chromadb 可用（RAG 可行性，spec §10 RAG step8）。

首次下 bge-large-zh（~1.3GB，hf-mirror）→ ingest 1 条历史 Bug → query 检索。
看 ref.used=True 即记忆库可用 → RAG 可行。
"""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# bge 下载复用 whisper 的 HF 镜像环境变量
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("REPROFORGE_MEMORY", "on")

from memory.store import MemoryStore
from agents.recall import recall
from agents.evidence import BugTimeline, TimelineEvent
from agents.regression import Issue

SMOKE_PATH = "./reproforge_memory_smoke"
if os.path.exists(SMOKE_PATH):
    shutil.rmtree(SMOKE_PATH)                       # 干净起跑

print("=== RAG 冒烟：验证 bge-large-zh + chromadb ===")
print("(首次下 bge-large-zh ~1.3GB，hf-mirror，请耐心)")
ms = MemoryStore(path=SMOKE_PATH)

# ingest 1 条历史 Bug（模拟之前复现过的）
issue = Issue(title="Bug1", expected="160", actual="80",
              suspected_files=["App.tsx"], minimal_steps=["1 改数量"], stable_rate="3/3")
timeline = BugTimeline(events=[TimelineEvent(event_id=0, target="qty-input")],
                       expected="160", actual="80")
ms.ingest_issue(issue, timeline, None)
print(f"ingest 完成，库内 {ms.col.count()} 条")

# query 相似（同样的 Bug 描述）
ref = recall(timeline, [], store=ms)
print(f"recall: used={ref.used}  命中 {len(ref.items)} 条")
if ref.items:
    print(f"  最近: {ref.items[0]['doc'][:60]}")
    print("[OK] RAG 记忆库可用 -> RAG 可行")
else:
    print("[WARN] 未检索到（bge 或 chromadb 异常）-> RAG 将降级")

shutil.rmtree(SMOKE_PATH, ignore_errors=True)       # 清理临时库
