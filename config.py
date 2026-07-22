"""ReproForge 双轨模型配置。

本地优先 + 远程 fallback：get_local_*_config 返回本地配置（无 LOCAL_* env 则 None），
get_remote_*_config 返回 Stepfun 远程。旧函数 get_model_config/get_vl_model_config 保留
（返回"主配置"= 本地 or 远程），向后兼容 eval/compare.py。
"""
import os
from dataclasses import dataclass


@dataclass
class ModelConfig:
    base_url: str
    model: str
    api_key: str
    is_local: bool = False


# —— 文本 ——
def get_local_model_config() -> ModelConfig | None:
    """本地文本 vLLM（spark-71 :8000）。无 LOCAL_BASE_URL → None（纯远程模式）。"""
    base = os.getenv("LOCAL_BASE_URL")
    if not base:
        return None
    return ModelConfig(
        base_url=base,
        model=os.getenv("LOCAL_MODEL", "qwen2.5-coder:7b"),
        api_key=os.getenv("LOCAL_API_KEY", "ollama"),
        is_local=True,
    )


def get_remote_model_config() -> ModelConfig:
    """远程 Stepfun step-3.7。"""
    return ModelConfig(
        base_url="https://api.stepfun.com/step_plan/v1",
        model=os.getenv("STEPFUN_MODEL", "step-3.7-flash"),
        api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
    )


# —— VL ——
def get_local_vl_config() -> ModelConfig | None:
    """本地 VL vLLM Qwen2.5-VL（spark-71 :8001）。无 LOCAL_VL_BASE_URL → None。"""
    base = os.getenv("LOCAL_VL_BASE_URL")
    if not base:
        return None
    return ModelConfig(
        base_url=base,
        model=os.getenv("LOCAL_VL_MODEL", "Qwen2.5-VL-7B-Instruct"),
        api_key=os.getenv("LOCAL_VL_API_KEY", "vllm"),
        is_local=True,
    )


def get_remote_vl_config() -> ModelConfig:
    """远程 Stepfun step-3.7 多模态。"""
    return ModelConfig(
        base_url="https://api.stepfun.com/step_plan/v1",
        model=os.getenv("VL_MODEL", "step-3.7-flash"),
        api_key=os.environ["STEPCONFIG_FUN_API_KEY"],
    )


# —— 向后兼容（eval/compare.py 等旧调用）——
def get_model_config() -> ModelConfig:
    """主文本配置：本地优先，无则远程。"""
    return get_local_model_config() or get_remote_model_config()


def get_vl_model_config() -> ModelConfig:
    """主 VL 配置：本地优先，无则远程。"""
    return get_local_vl_config() or get_remote_vl_config()
