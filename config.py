"""ReproForge 双轨模型配置（plan Task 1.1）
PROFILE=local → 本地模型；默认 → Stepfun 远程
"""
import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    base_url: str
    model: str
    api_key: str


def get_model_config() -> ModelConfig:
    if os.getenv("PROFILE") == "local":
        return ModelConfig(
            base_url=os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"),
            model=os.getenv("LOCAL_MODEL", "qwen2.5-coder:7b"),
            api_key=os.getenv("LOCAL_API_KEY", "ollama"),
        )
    return ModelConfig(
        base_url="https://api.stepfun.com/step_plan/v1",
        model=os.getenv("STEPFUN_MODEL", "step-3.7-flash"),
        api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
    )
