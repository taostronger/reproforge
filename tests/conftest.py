"""pytest 全局配置：load .env + 每个 test 重置 llm.client._client（隔离 mock）。"""
import os
from pathlib import Path
from dotenv import load_dotenv
import pytest

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("STEPCONFIG_FUN_API_KEY", "test-placeholder")


@pytest.fixture(autouse=True)
def reset_llm_client():
    import llm.client
    llm.client._client = None
    yield
    llm.client._client = None
