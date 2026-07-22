#!/usr/bin/env bash
# 本地三端口 SSH 隧道 → spark-71（文本:8000 / VL:8001 / bge:8002）
# 前台运行，Ctrl-C 断开。密码见 ssh信息/spark-71-连接指南.md
exec ssh -p 6071 -N \
  -L 8000:localhost:8000 \
  -L 8001:localhost:8001 \
  -L 8002:localhost:8002 \
  -o ServerAliveInterval=30 \
  Developer@106.13.186.155
