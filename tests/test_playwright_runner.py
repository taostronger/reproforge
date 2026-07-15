"""Task 2.2 测试：Playwright 测试运行器（mock subprocess，不真跑浏览器）。"""
from unittest.mock import patch, MagicMock

from test_runner.runner import run_test, run_n_times, RunResult, RunTimesResult


def _cp(returncode, stdout):
    """构造 subprocess.CompletedProcess 替身。"""
    cp = MagicMock()
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = ""
    return cp


def test_run_test_passed_on_success():
    with patch("test_runner.runner.subprocess.run") as m:
        m.return_value = _cp(0, '{"stats":{"passes":1,"failures":0,"unexpected":0,"flaky":0}}')
        r = run_test("tests/fixtures/ok.spec.ts")
    assert isinstance(r, RunResult) and r.passed is True


def test_run_test_failed_on_error():
    with patch("test_runner.runner.subprocess.run") as m:
        m.return_value = _cp(1, '{"stats":{"passes":0,"failures":1,"unexpected":1,"flaky":0}}')
        r = run_test("tests/fixtures/failing.spec.ts")
    assert isinstance(r, RunResult) and r.passed is False


def test_run_test_fallback_to_exitcode_when_json_bad():
    # stdout 非合法 JSON → 用 exit code 兜底（这里 exit 0 → passed）
    with patch("test_runner.runner.subprocess.run") as m:
        m.return_value = _cp(0, "not json at all")
        r = run_test("x.spec.ts")
    assert r.passed is True


def test_run_n_times_counts_pass_fail():
    outputs = [
        _cp(0, '{"stats":{"passes":1,"failures":0,"unexpected":0}}'),
        _cp(0, '{"stats":{"passes":1,"failures":0,"unexpected":0}}'),
        _cp(1, '{"stats":{"passes":0,"failures":1,"unexpected":1}}'),
    ]
    with patch("test_runner.runner.subprocess.run") as m:
        m.side_effect = outputs
        res = run_n_times("x.spec.ts", n=3)
    assert isinstance(res, RunTimesResult)
    assert res.pass_count == 2 and res.fail_count == 1
    assert res.stable_fail is False  # 非全失败


def test_run_n_times_stable_fail_when_all_fail():
    with patch("test_runner.runner.subprocess.run") as m:
        m.side_effect = [_cp(1, '{"stats":{"passes":0,"failures":1,"unexpected":1}}')] * 3
        res = run_n_times("x.spec.ts", n=3)
    assert res.fail_count == 3 and res.stable_fail is True
