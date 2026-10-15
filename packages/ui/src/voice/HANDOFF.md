# 语音增量交付

状态：本地纯模块与控件候选已完成，待总管按最终 Git SHA 审查/冻结；不代表正式 v2 已接入。

分支 `codex/website`，前置 UI `486294ac3255b08fdb13a307ee15f96c571020d9`；规范 `phase2-v1.0.0` + 正式放行 `d0af2804ed1ad70d3dd66e930582831bbd6b5e96` + 本机音色补正 `8fe35943d026c3d030c2dd42b2f889abe27f2422`。B3 精确来源及完整接线契约见 README。

文件范围仅 `packages/ui/src/voice/**` 和 `packages/ui/src/index.ts` 新增一行导出。controller/validation 管队列与最小投影，browser 适配本机 Web Speech 与生命周期，preferences 隔离个人偏好，controls 复用原 primitives。tests 与 harness 也仅在新 voice 目录。源文件 SHA-256 见 SOURCE-HASHES.json（不递归包含自身）；完整 Git 提交覆盖清单本身。

## 实际结果（分别计数）

| 检查 | 结果 |
| --- | --- |
| 新语音 `node --import tsx --test src/voice/tests/voice.test.mjs` | 32/32 通过，无实际音频 |
| 原公共 UI `pnpm test` | 13/13 通过，不计入上面 32 项 |
| `pnpm typecheck` | exit 0 |
| `pnpm build` | 共享 heavy lock 下 exit 0 |
| 编译产物 `compiled-smoke.mjs` | 最小导出、mock 播放/撤销通过，不当作新增单测计数 |
| 独立浏览器 | 15/15 无声断言，1440/390 两宽无页面水平溢出，warning/error 0 |

浏览器断言包括默认关闭、普通用户原创/引用、过滤与去重、逐订阅开关、22 点停播清队列、08 点不补播、超管同样可用个人设置、会话/断流、metadata 晚到、无本机音色、播放失败和全局关闭。节点单测另覆盖全部评级/错误 metadata/严格 ID、TTL、满队列、有界去重、超时、存储隔离、原生语音适配替身及页面生命周期。

首次语音单测为 31/32：跨夜重放用例错误地为同一个帧重新生成了次日 received_at；修正测试以保留真实重放的原始帧后最终 32/32。原失败结论保留在运行证据，不修改事件门槛或放宽断言。一次启动夹具被自动审批认为缺少语音授权而拒绝；只读核对总管原始 userMessage `01a1408f-3a29-7131-8d09-5bd123e05f81` 第④项后，对同一命令补充授权证据复核获准，未绕过或改用其他执行方式。

证据在忽略目录 `packages/ui/var/voice/`：浏览器 bundle 输入哈希 browser-inputs.json、15 项 browser-proof.json、两宽 mock 截图，以及 validation.json。构建锁回执 `chief-review-f19047ba-540f-44ff-95f4-53d360367813.json` exit 0；浏览器持锁进程回执 `chief-review-7a347942-7f87-420b-bce8-e2db8da4dc4b.json` 在验收后主动 Ctrl+C，exit 130 为正常手动收尾。harness 与临时页均已关闭，锁已释放；未与集成并行重跑重型任务。

## 未验证 / 集成责任

- 未实际扬声，未验证真实扬声器听感、各浏览器本机中文音色或实际自动播放策略；Web Speech 可能无本机音色，必须保留明确禁用状态。
- 未接真实 B1 session、现有 B3 EventSource 或实际只读 metadata；未执行正式 v2、公网权限/SSE撤销或来源联调。集成提供可信 user_id/epoch、准确 open/error/replay/撤销回调及成功 ID/revision 投影，并负责最终页面验收。
- 未新增 HTTP、后端、业务库或外部依赖；未修改旧 UI/页面、监控、真实来源、四库、Mac 后台任务、Cloudflare、部署、main 或其他 Worktree。

完成交付后保留候选供总管审查，后续修正只向前另提交。
