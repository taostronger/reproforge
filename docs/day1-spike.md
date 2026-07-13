# Day1 Spike 验证报告（2026-07-13）

## 结论：5/5 闸门全通过 → ReproForge 正式立项 GO

核心技术链路（浏览器采集 → 语音理解 → AI 生成测试 → Bug 复现 → 证据输出）全部验证可行。

## 5 项闸门结果

| 闸门 | 结果 | 证据 |
|---|---|---|
| ① 操作采集 | ✅ | Playwright trace.zip（43KB，含 goto/fill/click 4 事件 + 截图） |
| ② 语音理解 | ✅ | faster-whisper small 转写「我把数量改成2,总价还是80,应该是160」，提取出期望160 / 实际80 |
| ③ 测试生成 | ✅ | Stepfun `step-3.7-flash` 生成高质量 Playwright 测试，定位器用 data-testid，断言 `toHaveText('160')` |
| ④ Bug 复现 | ✅ | Bug1（优惠券不随数量更新）稳定复现：apply 后总价 80，改数量 2 后仍 80（应 160） |
| ⑤ 证据输出 | ✅ | out/trace.zip + spike/generated_test.spec.ts 均生成 |

> 闸门③ 是 ReproForge 的核心（AI 理解 Bug → 生成可运行测试），质量超预期。

## 被测 Demo

React + Vite 商城（`demo_project/`），预埋 3 个 Bug：
1. 优惠券总价 apply 时只算一次，数量变化不重算（Bug1，Spike 用）
2. 优惠码输入框 onChange 不清除旧错误提示
3. 删除商品后若曾 apply 优惠码，总价不归零

## 解决的环境问题（后续开发沿用，重要）

1. **GitHub HTTPS 被墙、SSH 通**：spark-71 不能 https 访问 github.com（443 超时），但 ssh:22 通。已生成 ed25519 key 配到 GitHub，用 `git@github.com:` 协议提交。
2. **plink 非交互 shell 不读 .bashrc**：每次远程跑 node/npm 必须显式 `. $HOME/.nvm/nvm.sh`（.bashrc 里已有 nvm 初始化，但非交互 shell 不加载）。
3. **HuggingFace 被墙 + Xet 协议 401**：whisper 模型下载必须设两个环境变量：
   - `HF_ENDPOINT=https://hf-mirror.com`（国内镜像）
   - `HF_HUB_DISABLE_XET=1`（禁用新版 Xet CAS 协议，它走 cas-server.xethub.hf.co 需认证且镜像不覆盖）
   - 模型首次下载后缓存在 `~/.cache/huggingface`，后续运行免联网。
4. **pip / npm 源**：pypi.org、registry.npmjs.org 直连可用；清华 PyPI 镜像 / npmmirror 作备用。
5. **无 sudo**：Node 用 nvm（用户态）装；chromium-headless-shell 自带依赖，无 sudo 也能 launch。

## 双轨模型验证

- 开发期 Stepfun `step-3.7-flash`（远程 API）已验证可用，生成质量高。
- Demo 期将切本地模型（spark-71 qwen3.6:35b / Ollama），模型抽象层保证零代码切换（待 Phase 1 实现）。

## 下一步：Phase 1 · 基础设施

config 双轨模型层 → 模型抽象（OpenAI 兼容）→ Playwright 录制器 → Trace 解析器 → ASR。详见 `docs/superpowers/plans/2026-07-13-reproforge.md`。
