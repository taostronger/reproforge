#!/usr/bin/env bash
# VL vLLM（spark-71 :8001，util 0.3，Qwen2.5-VL-7B；0.4 与文本 0.45 共存会占满 119G，降 0.3 留余量）
# 注意：--limit-mm-per-prompt 参数名按 vLLM 0.23.1rc1 实测，新版可能为 --limit-mm-per-request
set -e
docker rm -f vllm-vl 2>/dev/null || true
docker run -d --name vllm-vl --net=host --ipc=host --gpus all \
  --ulimit nofile=1048576:1048576 \
  -e VLLM_USE_DEEP_GEMM=0 \
  -v /home/Developer/models:/models \
  eugr/spark-vllm:latest \
  vllm serve /models/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8001 \
    --tensor-parallel-size 1 --gpu-memory-utilization 0.3 \
    --max-model-len 8192 --limit-mm-per-prompt '{"image": 1}' \
    --max-num-batched-tokens 4096 --enable-prefix-caching
echo "vllm-vl 启动中（预热 2-3 分钟），日志：docker logs -f vllm-vl"
