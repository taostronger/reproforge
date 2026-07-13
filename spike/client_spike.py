"""Task 0.4 Spike: Stepfun API 生成 Playwright 测试
闸门3(测试生成): 模型能输出含正确断言的 Playwright 测试
读取 .env 中的 STEPCONFIG_FUN_API_KEY
"""
import os
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = OpenAI(
    base_url="https://api.stepfun.com/step_plan/v1",
    api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
)

PROMPT = """你是测试工程师。根据用户口述生成一个 Playwright (TypeScript) 测试。
用户口述：{narration}
被测页面：http://localhost:5173
关键元素（用 data-testid 定位）：
- 优惠码输入框: [data-testid=coupon-input]
- 应用按钮: [data-testid=apply-btn]
- 数量框: [data-testid=qty-input]
- 总价: [data-testid=total-price]
操作顺序：goto 页面 → 优惠码填 SALE20 → 点应用 → 数量填 2 → 断言总价。
要求：
1. 用 `test('...', async ({{ page }}) => {{ ... }})` 语法
2. 断言 total-price 文本为用户期望值
3. 只输出测试代码块（```ts ... ```），不要解释。"""


def generate_test(narration):
    resp = client.chat.completions.create(
        model="step-3.7-flash",
        messages=[{"role": "user", "content": PROMPT.format(narration=narration)}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


if __name__ == "__main__":
    narration = "我把数量改成2，总价还是80，应该是160"
    print("=== 调用 Stepfun step-3.7-flash 生成测试 ===")
    raw = generate_test(narration)
    print("--- 模型输出(前600字) ---")
    print(raw[:600])

    m = re.search(r"```(?:typescript|ts|js|javascript)?\n(.*?)```", raw, re.S)
    code = m.group(1) if m else raw
    out = Path(__file__).resolve().parent / "generated_test.spec.ts"
    out.write_text(code, encoding="utf-8")

    print("\n=== 闸门3: 测试生成质量 ===")
    print(f"  保存到: {out}")
    print(f"  含 expect 断言: {'expect' in code}")
    print(f"  含 total-price: {'total-price' in code}")
    print(f"  含期望值 160: {'160' in code}")
