"""config 双轨拆分测试：本地/远程配置的 None/返回逻辑。"""
from config import (ModelConfig, get_local_model_config, get_remote_model_config,
                    get_local_vl_config, get_remote_vl_config, get_model_config)


def test_get_local_model_config_no_env_returns_none(monkeypatch):
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    assert get_local_model_config() is None


def test_get_local_model_config_with_env(monkeypatch):
    monkeypatch.setenv("LOCAL_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("LOCAL_MODEL", "/models/qwen36")
    monkeypatch.setenv("LOCAL_API_KEY", "vllm")
    cfg = get_local_model_config()
    assert cfg is not None
    assert cfg.base_url == "http://localhost:8000/v1"
    assert cfg.model == "/models/qwen36"
    assert cfg.is_local is True


def test_get_remote_model_config(monkeypatch):
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_remote_model_config()
    assert "stepfun" in cfg.base_url
    assert cfg.model == "step-3.7-flash"
    assert cfg.is_local is False


def test_get_local_vl_config_no_env_returns_none(monkeypatch):
    monkeypatch.delenv("LOCAL_VL_BASE_URL", raising=False)
    assert get_local_vl_config() is None


def test_get_local_vl_config_with_env(monkeypatch):
    monkeypatch.setenv("LOCAL_VL_BASE_URL", "http://localhost:8001/v1")
    monkeypatch.setenv("LOCAL_VL_MODEL", "Qwen2.5-VL-7B-Instruct")
    cfg = get_local_vl_config()
    assert cfg.base_url == "http://localhost:8001/v1"
    assert cfg.is_local is True


def test_get_remote_vl_config(monkeypatch):
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_remote_vl_config()
    assert "stepfun" in cfg.base_url
    assert cfg.is_local is False


def test_get_model_config_no_local_falls_back_to_remote(monkeypatch):
    """无 LOCAL_BASE_URL → get_model_config 返回远程（向后兼容 eval/compare.py）。"""
    monkeypatch.delenv("LOCAL_BASE_URL", raising=False)
    monkeypatch.setenv("STEPCONFIG_FUN_API_KEY", "testkey")
    cfg = get_model_config()
    assert "stepfun" in cfg.base_url
