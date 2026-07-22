"""spark-71 模型下载（modelscope 源，国内快，不走 Xet CAS）。

用法：python modelscope_download.py
hf-mirror 对大文件走 Xet CAS 易超时，Qwen 官方在 modelscope 有完整镜像。
"""
from modelscope import snapshot_download

HOME = "/home/Developer"

print("[1/2] modelscope 下 Qwen2.5-VL-7B-Instruct (~15GB)...", flush=True)
snapshot_download('Qwen/Qwen2.5-VL-7B-Instruct',
                  local_dir=f'{HOME}/models/Qwen2.5-VL-7B-Instruct')
print("[2/2] modelscope 下 bge-large-zh-v1.5 (~1.3GB)...", flush=True)
snapshot_download('BAAI/bge-large-zh-v1.5',
                  local_dir=f'{HOME}/models/bge-large-zh-v1.5')
print("MS_ALL_DONE", flush=True)
