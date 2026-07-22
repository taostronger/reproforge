#!/usr/bin/env bash
# 在 spark-71 执行：下 Qwen2.5-VL-7B + bge-large-zh（走 hf-mirror，避免流量费）
set -e
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1

echo "[1/2] 下载 Qwen2.5-VL-7B-Instruct (~15GB)..."
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct \
  --local-dir ~/models/Qwen2.5-VL-7B-Instruct

echo "[2/2] 下载 bge-large-zh-v1.5 (~1.3GB)..."
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir ~/models/bge-large-zh-v1.5

echo "完成：~/models/Qwen2.5-VL-7B-Instruct + ~/models/bge-large-zh-v1.5"
