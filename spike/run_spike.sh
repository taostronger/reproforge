#!/usr/bin/env bash
# Day1 Spike 串联：在 spark-71 上验证 5 项闸门
# 前提：已在项目根目录、.venv 已建、demo_project 已 npm run dev(5173)
set -u
cd "$(dirname "$0")/.."
. .venv/bin/activate
. "$HOME/.nvm/nvm.sh" 2>/dev/null

echo "########## 闸门1+4+5: 操作采集 / Bug1复现 / 证据输出 ##########"
python spike/recorder_spike.py
echo

echo "########## 闸门3: 测试生成(Stepfun) ##########"
python spike/client_spike.py
echo

echo "########## 闸门2: 语音理解(faster-whisper) ##########"
if [ -f spike/sample.wav ]; then
  python spike/transcribe_spike.py spike/sample.wav
elif command -v edge-tts >/dev/null 2>&1; then
  echo "用 edge-tts 生成测试音频..."
  edge-tts --voice zh-CN-XiaoxiaoNeural \
    --text "我把数量改成2，总价还是80，应该是160" \
    --write-media spike/sample.wav 2>/dev/null
  python spike/transcribe_spike.py spike/sample.wav
else
  echo "无 sample.wav 且无 edge-tts，尝试安装 edge-tts..."
  pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple edge-tts 2>/dev/null
  if command -v edge-tts >/dev/null 2>&1; then
    edge-tts --voice zh-CN-XiaoxiaoNeural --text "我把数量改成2，总价还是80，应该是160" --write-media spike/sample.wav 2>/dev/null
    python spike/transcribe_spike.py spike/sample.wav
  else
    echo "SKIP闸门2: 陶壮可本地录5秒音频上传到 spike/sample.wav 后重跑"
  fi
fi
echo

echo "########## 闸门5: 证据产物清单 ##########"
ls -la out/trace.zip spike/generated_test.spec.ts 2>/dev/null
echo "SPIKE_DONE"
