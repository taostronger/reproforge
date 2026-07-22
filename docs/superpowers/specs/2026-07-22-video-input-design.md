# D: 视频输入（上传视频 → 生成所有信息）

> 日期：2026-07-22 · 状态：待开发 · 作者：tz（taostronger 队）

## 1. 目标

上传测试员录的**视频**（边操作商城边口述）→ 自动生成 **actions + segments + screenshot** → 喂 run_pipeline。最灵活的输入方式（事后录视频上传，不用实时操作/预填）。

与 A/B/C 互补：
- A 预填 JSON（最简）
- C 实时录制（Playwright 监听，要桌面活跃）
- **D 视频上传**（事后视频，任意设备录）

## 2. 流水线

```
上传视频（.mp4，操作+口述）
   │
   ├─▶ 提音频（imageio-ffmpeg）→ ASR（faster-whisper small, CPU int8）→ segments（口述文本，带时间戳）
   │
   ├─▶ segments → LLM（step-3.7）提 actions（type/target/value，target=data-testid 语义推断）
   │
   └─▶ 抽帧（opencv，中间偏后）→ screenshot（喂 VL 视觉）
   │
   ▼
填回 UI：actions_json / narration / screenshot → 点「运行复现流水线」
```

**为什么用口述提 actions 而非 VL 看视频帧**：口述里测试员已说清每步操作（"我填了 SALE20 点应用 改数量2"），LLM 从口述语义映射 testid（coupon-input/apply-btn/qty-input）比 VL 逐帧识别操作更可靠；视频帧只抽一张作 VL 截图输入。

## 3. `capture/video_parser.py`

```python
def video_to_segments(video_path) -> list[Segment]
    # imageio-ffmpeg 提音频到 wav(16k mono) → faster-whisper(small,cpu,int8) 转写 → Segment 列表

def segments_to_actions(segments) -> list[dict]
    # 口述拼成文本 → LLM(chat_json) 输出 {"actions":[{type,target,value,text},...]}
    # target 用 data-testid 推断；补 timestamp/text；失败/口述空 → []

def video_to_screenshot(video_path, at_ratio=0.7) -> str|None
    # opencv 抽中间偏后帧 → png 路径；失败 → None

def parse_video(video_path) -> (actions, narration_text, screenshot_path)
    # 组合上面三步，UI 调这个
```

## 4. UI 改动（`ui/app.py`）

- 加 `gr.Video` 上传框（label「上传操作视频（可选，自动生成 actions/口述/截图）」）
- 加「🎬 从视频生成」按钮 → 调 `parse_video` → 把 actions 填回 `actions_json`、口述填回 `narration`、截图填回 `screenshot`

## 5. 降级链（不阻塞）

| 触发 | 行为 |
|---|---|
| 视频无音轨 / ASR 失败 | segments 空 → narration 空 + actions 空（提示用户手填/录制）|
| LLM 提 actions 失败 | actions 空（提示）|
| 抽帧失败 | screenshot None（VL 跳过）|
| 视频处理整体失败 | 提示 + 不改 UI（回退预填/录制）|

## 6. 测试（`tests/test_video_parser.py`）

全 mock（不真跑 ffmpeg/whisper/LLM）：
- `video_to_segments`：mock subprocess（提音频）+ mock WhisperModel.transcribe → segments
- `segments_to_actions`：mock chat_json → actions；口述空 → []
- `video_to_screenshot`：mock cv2 → png；失败 → None
- `parse_video`：组合 mock

真跑（提音频+ASR+LLM+抽帧）留端到端冒烟（需真视频文件）。

## 7. 依赖

- `opencv-python` / `imageio-ffmpeg` / `faster-whisper`（已装）
- whisper `small` 模型（首次 ASR 时 hf-mirror 下载 ~480MB，复用 `HF_ENDPOINT`/`HF_HUB_DISABLE_XET`）
- step-3.7（LLM 提 actions + VL 看截图）

## 8. 非目标

- VL 看视频帧逐帧提 actions（用口述，更可靠）
- 视频编辑/剪辑/转码选项
- 多视频/拼接

## 9. 风险

- **target 推断质量**：LLM 从口述映射 testid，依赖口述清晰 + 商城 testid 语义直观（coupon-input 等 LLM 易猜）。复杂商城可能不准 → reproduction 的 fix_locator 兜底。
- **ASR 中文质量**：small 模型中文一般，口述要清晰。必要时升 medium（更大）。
- **首次 whisper 下载**：~480MB，hf-mirror，首次 ASR 慢（后续缓存）。
