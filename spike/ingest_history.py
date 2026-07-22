"""灌入示例历史 Bug 到记忆库（让 recall 有数据可检索，demo 不再空库）。

用法：python spike/ingest_history.py（需 EMBEDDING_BASE_URL + 隧道 :8002）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv()

from memory.store import get_memory_store
from agents.evidence import BugTimeline, TimelineEvent
from agents.regression import Issue

store = get_memory_store()
if store is None:
    print("✗ store 未启用（EMBEDDING_BASE_URL 未设 / bge 服务不通 / 隧道未开）")
    sys.exit(1)

# 示例历史 Bug（商城常见，覆盖用户当前 Bug 类型，让 recall 能命中相似案例）
BUGS = [
    Issue(title="优惠券不随商品数量重新计算总价",
          expected="160", actual="80",
          minimal_steps=["fill coupon-input SALE20", "click apply-btn", "fill qty-input 2"],
          stable_rate="3/3", suspected_files=["src/App.tsx"]),
    Issue(title="优惠码输入框不清除旧错误提示",
          expected="无错误提示", actual="仍显示旧错误",
          minimal_steps=["fill coupon-input WRONG", "click apply-btn", "fill coupon-input SALE20"],
          stable_rate="3/3", suspected_files=["src/App.tsx"]),
    Issue(title="删除商品后总价不归零",
          expected="0", actual="仍显示旧总价",
          minimal_steps=["click remove-btn"], stable_rate="3/3", suspected_files=["src/App.tsx"]),
    Issue(title="商品数量输入非数字导致总价 NaN",
          expected="优雅处理或提示", actual="总价显示 NaN",
          minimal_steps=["fill qty-input abc"], stable_rate="2/3", suspected_files=["src/App.tsx"]),
    Issue(title="加入购物车按钮不更新数量",
          expected="数量+1", actual="数量不变",
          minimal_steps=["click add-1"], stable_rate="3/3", suspected_files=["src/App.tsx"]),
    Issue(title="总价小计与优惠后价格不一致",
          expected="总价=小计×折扣", actual="总价与小计脱节",
          minimal_steps=["fill coupon-input SALE20", "click apply-btn", "fill qty-input 3"],
          stable_rate="3/3", suspected_files=["src/App.tsx"]),
]

for issue in BUGS:
    tl = BugTimeline(
        events=[TimelineEvent(event_id=0, action="click", target="total-price",
                              value="", user_narration=issue.title)],
        expected=issue.expected, actual=issue.actual,
    )
    store.ingest_issue(issue, tl, None)
    print(f"  [OK] ingest: {issue.title}")

print(f"\n记忆库现有 {store.col.count()} 条历史 Bug（recall 节点可检索）")
