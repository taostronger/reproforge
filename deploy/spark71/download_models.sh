#!/usr/bin/env bash
# spark-71 下模型（modelscope 源，国内快、不走 Xet CAS）
# 实测：hf-mirror 对大文件(safetensors)走 Xet CAS 易 "read operation timed out"，
# Qwen 官方在 modelscope 有完整镜像，速度更稳。用 ~/reproforge/.venv（有 modelscope）。
set -e
PYTHON=${PYTHON:-$HOME/reproforge/.venv/bin/python}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
$PYTHON "$SCRIPT_DIR/modelscope_download.py"
