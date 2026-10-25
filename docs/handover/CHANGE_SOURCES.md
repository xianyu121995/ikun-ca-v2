# 线上主线与改动来源

主线应用基线：ab3b3d768895741f9a4b36d13568ff5de2245ff4。不是把05e0ca2整条分支合进来；它只有语音候选未上线，已单独保留。

## 已部署应用提交

| 完整提交 | 来源 | 线上作用 |
| --- | --- | --- |
| aeca6bbbc1b09f1a3e25a82dbd803357972fca9e | codex/integration | 当时已整合的Web/Auth/Projects/Hunter/Tracking基础；生态未提交改动不属于该提交 |
| fd6a31b02afe52124024f3ac219a747082725811 | codex/wss-receive-audit，后并入quota链 | 脱敏WSS收件诊断 |
| 8246f679bce60b9bcb3e2fcb2b07683154c81595 | published-feed语音链 | 以published-v1新增activity驱动语音 |
| f5a0525909cfd7ace3ce09e29d3e9e35e233a793 | codex/voice-published-feed | 到达期限与重连时语音所有权 |
| ce38b503dacbf2dfd29f354e6214dfa8edb5325a | codex/desktop-auth-ssh | 桌面账号工具SSH到Tokyo，网址ikun.ca |
| a7e4637c921a910d25effbede56ae77575adb2fd | codex/tracking-wss-quota | Watch核对/额度失败不能拦已订阅WSS |
| 43c9ceacfaaa3bcce3e2fd02e7a8629fd98690a4 | 同上 | release overlay验证 |
| 2794a0f752ab0631e761d545d8ab777b26ab6bd4 | 同上 | WSS401脱敏诊断 |
| 663a4ee9a0467fb0896df9ebb236068e36450ab5 | 同上 | 共享6551预算/熔断、事件驱动Watch核对、退避 |
| 61f9fe494c79ef28793c26438ae3b75428302f2a | 同上 | 有限缺口补拉代码；现默认关闭，不是当前启用功能 |
| 80b52054361a6f47b55e8471208aed0455f34a65 | 同上 | 网站部署关停与就绪保护 |
| 7fa16d69fdbc8c7151c46b0dbbcc29b92cc106fb | 同上；Web/Tracking实际release | 被动WSS，所有Tracking补拉入口关闭、预算0 |
| 7111ce3c47b09c497e124bfe793ed74366b89ebd | codex/hunter-rest-batches | Hunter REST-only、12批持久调度、计费保护 |
| ab3b3d768895741f9a4b36d13568ff5de2245ff4 | 同上；Hunter实际release | 微秒窗口精度修复；ikun/live应用基线 |

Git历史保留上述来源，不做main合并、squash或改写冻结提交。Projects进程仍在75dd1907e7ddcad481b4de8523963b5fe15198ae，但56个Projects源码文件与本主线一致；不是给它补做一次重启。

## 本次从线上回收的运维文件

- release-integration/lightsail/production_ops.py：准确复制/比对服务器已部署版本。REST-only Hunter的退休Watch状态过滤原先只在服务器，现归档；不是本次上线新健康逻辑。
- run_hunter_timefix_ab3b3d768895.py：当前实际固定release启动器。
- run_hunter_rest_7111ce3.py：历史固定启动器，保留来源；不可当成推荐回滚版本。
- deployed-systemd/：现存七类服务、两个timer及Hunter固定版本drop-in原件，存档而不安装。
- run_production.py、verified_backup.py与服务器逐字hash核对；原本相同部分不人为生成改动。
- docs/handover/live-inventory.json：服务、版本、端口、私有配置路径和非秘密配置值、DB schema、备份核验。
- source-verification.json：Web310、Tracking25、Hunter34、Projects56个应用文件比较，425个一致，缺失0、不符0。不包含生成二进制/.next逐字比较，不把本地构建哈希冒称服务器构建。

## 本次仅本地验收和文档的改动

- release-integration/handover/：可重跑的隔离回归入口、禁止外部网络/AI的pytest保护、测试报告。
- Auth、Projects、Tracking测试装配：Node/Python不再绑定旧Mac绝对路径；从当前源码而非缺失的冻结preview导入；共享Python运行时随隔离测试包一并装配。
- SSE用例改测实际 /api/v1/tracking/events 入口并容许先到的注释心跳，继续校验认证撤销、上游取消和事件结构。两个会话旋转用例显式配置5个fixture会话；生产1设备规则不变。
- 上述为测试/说明，不修改425个线上应用源码。用户要求干净主线可复验，因此修复测试环境而不降低生产业务断言。
- HANDOVER.md：操作边界、版本映射、凭据位置、部署/回滚/恢复、权限与待办。任何部署/SSH变更命令本次均未执行。

## 未部署，等用户批准

| 分支 | 来源与状态 |
| --- | --- |
| codex/pending-voice-approval | 从本主线相同应用基线ab3b3d7创建，仅cherry-pick 05e0ca277b398fdc17151eafa1e78b72f6d25c89为1ad448b，最终状态文档提交966cbd6f8a13a4ebe04359eca732fcfda4483048；3秒确认、转推撤回；未部署 |
| codex/ecosystem | 9f243bc3076d2ddc2efccc6c34a7a45c03a065f5；原integration worktree的25个既有改动独立保存；基于aeca6bb；未部署 |
| codex/tracking-wss-quota | 原分支05e0ca2原样保留；整条HEAD不是当前线上版本，不能直接部署 |

生态本次389项离线通过、TS通过，原首轮失败证据保留。pending-voice新分支的实际验收和最终SHA见其HANDOVER-STATUS.md。上述任何分支都没并入main或生产。
