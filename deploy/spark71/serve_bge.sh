#!/usr/bin/env bash
# bge embedding 服务（spark-71 :8002，CPU）
# 先 scp deploy/spark71/bge_server.py 到 ~/reproforge_serve/
set -e
mkdir -p ~/reproforge_serve
# 用 ~/reproforge/.venv（已装 sentence-transformers+torch）；comfyui-env 路径在该机器不一致且有缺失
PYTHON=${PYTHON:-$HOME/reproforge/.venv/bin/python}
cd ~/reproforge_serve
nohup "$PYTHON" -m uvicorn bge_server:app --host 0.0.0.0 --port 8002 > bge.log 2>&1 &
echo "bge 启动 :8002（CPU），日志：~/reproforge_serve/bge.log"
