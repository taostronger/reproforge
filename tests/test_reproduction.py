"""Task 2.4 测试：Agent2 复现工程（mock chat + runner，不真跑浏览器/LLM）。"""
from unittest.mock import patch, MagicMock

from agents.reproduction import generate_test, fix_locator, reproduce, ReproductionResult
from agents.evidence import BugTimeline, TimelineEvent
from test_runner.runner import RunResult, RunTimesResult


def _timeline():
    return BugTimeline(
        events=[TimelineEvent(event_id=0, action="fill", target="qty-input",
                              value="2", user_narration="数量改2")],
        expected="160", actual="80",
    )


def test_generate_test_calls_chat():
    with patch("agents.reproduction.chat") as m:
        m.return_value = "test('x', async ({page}) => { await page.goto('/'); });"
        code = generate_test([{"type": "fill", "target": "qty-input", "value": "2", "text": "数量"}], "160", "80")
    assert "test(" in code
    m.assert_called_once()


def test_generate_test_strips_markdown_fence():
    # 真实 LLM 常把代码包在 ```ts ... ``` 围栏里；真跑前必须剥离
    raw = "```ts\ntest('x', async ({page}) => { await page.goto('/'); });\n```"
    with patch("agents.reproduction.chat", return_value=raw):
        code = generate_test([{"type": "fill", "target": "qty-input", "value": "2", "text": "数量"}], "160", "80")
    assert "```" not in code
    assert "test(" in code


def test_generate_test_ensures_import():
    # 即使 LLM 漏了 import，generate_test 应补上（否则真跑 ReferenceError: test is not defined）
    with patch("agents.reproduction.chat", return_value="test('x', async ({page}) => { await page.goto('/'); });"):
        code = generate_test([{"type": "fill", "target": "qty-input", "value": "2", "text": "数量"}], "160", "80")
    assert "@playwright/test" in code
    assert "import" in code


def test_fix_locator_calls_chat():
    with patch("agents.reproduction.chat") as m:
        m.return_value = "fixed code"
        out = fix_locator("orig spec", "strict mode violation")
    assert out == "fixed code"


def test_reproduce_stable_fail_triggers_minimize():
    tl = _timeline()
    run_n = MagicMock(return_value=RunTimesResult(
        pass_count=0, fail_count=3, results=[RunResult(False)] * 3))
    run_t = MagicMock(return_value=RunResult(False))
    with patch("agents.reproduction.chat", return_value="spec code"), \
         patch("agents.reproduction.minimize") as mmin:
        mmin.return_value = MagicMock(original_count=1, minimized_count=1, removed_count=0)
        res = reproduce(tl, run_test_fn=run_t, run_n_fn=run_n)
    assert isinstance(res, ReproductionResult)
    assert res.success is True
    assert res.rounds == 0          # 首轮即稳定失败，未修定位器
    mmin.assert_called_once()       # 触发了最小化


def test_reproduce_locator_repair_caps_at_two_rounds():
    tl = _timeline()
    unstable = RunTimesResult(pass_count=1, fail_count=2,
                              results=[RunResult(True), RunResult(False), RunResult(False)])
    run_n = MagicMock(return_value=unstable)
    run_t = MagicMock(return_value=RunResult(False))
    with patch("agents.reproduction.chat") as mchat, \
         patch("agents.reproduction.minimize") as mmin:
        mchat.return_value = "spec"
        res = reproduce(tl, run_test_fn=run_t, run_n_fn=run_n)
    assert res.success is False
    assert res.reason == "unstable"
    assert mchat.call_count == 3    # 1 次 generate + 2 次 fix_locator
    mmin.assert_not_called()        # 未稳定，不最小化


def test_reproduce_all_pass_is_no_bug():
    tl = _timeline()
    run_n = MagicMock(return_value=RunTimesResult(
        pass_count=3, fail_count=0, results=[RunResult(True)] * 3))
    run_t = MagicMock(return_value=RunResult(True))
    with patch("agents.reproduction.chat", return_value="spec"), \
         patch("agents.reproduction.minimize") as mmin:
        res = reproduce(tl, run_test_fn=run_t, run_n_fn=run_n)
    assert res.success is False
    assert res.reason == "no_bug"
    mmin.assert_not_called()        # 没最小化
