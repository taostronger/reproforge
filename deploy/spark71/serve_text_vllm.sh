#!/usr/bin/env bash
# 文本 vLLM（spark-71 :8000，util 0.45，与 VL 共存腾显存）
# 复用现有镜像/模型，仅改 util 0.8→0.45；必须带 DeepGEMM=0
set -e
docker rm -f vllm-text 2>/dev/null || true
docker run -d --name vllm-text --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 \
  -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models \
  eugr/spark-vllm:latest \
  vllm serve /models/qwen36-35b-a3b --host 0.0.0.0 --port 8000 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.45 \
    --max-model-len 8192 --max-num-batched-tokens 4096 \
    --load-format fastsafetensors --kv-cache-dtype fp8 --enable-prefix-caching
echo "vllm-text 启动中（预热 2-3 分钟），日志：docker logs -f vllm-text"
