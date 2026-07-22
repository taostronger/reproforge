"""spark-71 模型下载（python API，兼容 huggingface_hub 1.23 新 CLI）。

用法：python download_py.py（走 hf-mirror，避免流量费）
"""
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from huggingface_hub import snapshot_download

HOME = os.path.expanduser("~")

print("[1/2] 下载 Qwen2.5-VL-7B-Instruct (~15GB)...", flush=True)
snapshot_download("Qwen/Qwen2.5-VL-7B-Instruct",
                  local_dir=f"{HOME}/models/Qwen2.5-VL-7B-Instruct")
print("[2/2] 下载 bge-large-zh-v1.5 (~1.3GB)...", flush=True)
snapshot_download("BAAI/bge-large-zh-v1.5",
                  local_dir=f"{HOME}/models/bge-large-zh-v1.5")
print("ALL_DONE", flush=True)
