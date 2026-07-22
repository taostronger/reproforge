#!/usr/bin/env bash
# 编排：下模型 → 起三服务 → 健康检查
set -e
cd "$(dirname "$0")"

echo "=== 0. 模型（已下则跳过）==="
if [ ! -d ~/models/Qwen2.5-VL-7B-Instruct ] || [ ! -d ~/models/bge-large-zh-v1.5 ]; then
  bash download_models.sh
fi

echo "=== 1. 文本 vLLM :8000 ==="
bash serve_text_vllm.sh
echo "=== 2. VL vLLM :8001 ==="
bash serve_vl_vllm.sh
echo "=== 3. bge :8002 ==="
bash serve_bge.sh

echo "=== 等待预热（vLLM 各 2-3 分钟）==="
sleep 5
echo "健康检查（vLLM 未就绪属正常，稍后重试）："
for p in 8000 8001 8002; do
  echo -n "port $p: "
  curl -s --max-time 3 http://localhost:$p/v1/models && echo "" || echo "not ready"
done
