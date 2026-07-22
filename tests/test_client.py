"""client fallback 测试：本地优先，失败降级远程，都失败 raise。

全 mock _call（不触真实 openai/网络），验证 fallback 编排逻辑。
"""
import httpx
import pytest
from unittest.mock import patch, MagicMock


def _cfg(url, local=False):
    return MagicMock(base_url=url, model="m", api_key="k", is_local=local)


def test_chat_local_success_does_not_touch_remote():
    """本地成功 → _call 只调 1 次，参数是 local cfg。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", return_value="本地结果") as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "本地结果"
        assert mock_call.call_count == 1
        assert mock_call.call_args_list[0].args[0] is local


def test_chat_local_connection_error_falls_back_to_remote():
    """本地 httpx.ConnectError → fallback 远程，_call 调 2 次（local→remote）。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call",
               side_effect=[httpx.ConnectError("no local"), "远程结果"]) as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"
        assert mock_call.call_count == 2
        assert mock_call.call_args_list[1].args[0] is remote


def test_chat_local_timeout_falls_back_to_remote():
    """本地 httpx.TimeoutException → fallback 远程。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call",
               side_effect=[httpx.TimeoutException("slow"), "远程结果"]):
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"


def test_chat_no_local_goes_straight_to_remote():
    """无本地配置（None）→ 直接远程，_call 只 1 次，参数是 remote。"""
    remote = _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=None), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", return_value="远程结果") as mock_call:
        from llm.client import chat
        assert chat([{"role": "user", "content": "hi"}]) == "远程结果"
        assert mock_call.call_count == 1
        assert mock_call.call_args_list[0].args[0] is remote


def test_chat_both_fail_raises():
    """本地+远程都失败 → 不吞异常，raise（业务层降级）。"""
    local, remote = _cfg("http://local", True), _cfg("http://remote")
    with patch("llm.client.get_local_model_config", return_value=local), \
         patch("llm.client.get_remote_model_config", return_value=remote), \
         patch("llm.client._call", side_effect=httpx.ConnectError("all dead")):
        from llm.client import chat
        with pytest.raises(httpx.ConnectError):
            chat([{"role": "user", "content": "hi"}])


def test_chat_vision_uses_vl_configs():
    """chat_vision 走 VL 的 local/remote 配置。"""
    local, remote = _cfg("http://vl-local", True), _cfg("http://vl-remote")
    with patch("llm.client.get_local_vl_config", return_value=local), \
         patch("llm.client.get_remote_vl_config", return_value=remote), \
         patch("llm.client._call", return_value='{"expected":"x"}') as mock_call:
        from llm.client import chat_vision
        chat_vision([{"role": "user", "content": "..."}])
        assert mock_call.call_args_list[0].args[0] is local
