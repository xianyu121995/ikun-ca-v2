# v2 语音网站升级与公网验收报告

状态 **PASS_VOICE_PROTECTED_V2_WEB_ONLY_PUBLIC**。用户在本聊天直接批准的候选 `19863b2af031fc2592bb6d73b7161efc77b0bd1d` 已于 2026-10-16 14:05（上海时间）升级到 [受保护 v2](https://v2.ikun.ca/tracking)，14:14 完成公网验收。生产 BUILD_ID 为 `toKW74u9T1cCk_lyTUZXo`，实际部署的 **328 个源码哈希、271 个构建哈希全部匹配**。此前缺少直接批准的自动审批拒绝已由本次明确授权解除；历史记录保存在机器报告的 `historical_preapproval`，未绕过审批执行。

仅升级新 v2 网站及其既有受托管 Projects 私有 IPC。两个 Worker 保持原进程、原代码和原配置；未合入后续 501 候选，未修改 main、旧版服务、主域名、Cloudflare 或共享 Watch。左侧名称为“猎手项目追踪”。本报告确认本次受保护网站升级通过，不代表真实平台采集链路或主域名正式上线验收通过。

| 检查项 | 实际结果 |
| --- | --- |
| 网站 launchd | `ca.ikun.v2.c0lite.web`，PID `25136 → 67800`，仅网站重启 |
| Hunter launchd | `ca.ikun.v2.c0lite.hunter`，PID `2608 → 2608`，release `75b81a2b5210e41bdf8522467c7fba2a6a6e693c` |
| Tracking launchd | `ca.ikun.v2.c0lite.tracking`，PID `25225 → 25225`，release `64088893841122491aba508fdb514507db3d9339` |
| 原 Tunnel | `ca.ikun.v2.c0lite.tunnel`，PID `39523`；本轮无修改或重启 |
| Worker 配置 | 原两份 env、两份 plan、两份 plist 前后 SHA256 一致；Tracking 私密配置符合原冻结 receipt 哈希 |
| 四库 | Auth v2、Projects v2、Hunter v4、Tracking v4；四个不同 inode，均 0600、单链接；identity、integrity、FK 通过；无覆盖或 schema 迁移 |
| 备份 | 升级前、升级后、临时账号禁用后各在线备份四库；12 份哈希复核通过，备份 integrity/FK 通过 |
| 生产模式 | `next start --hostname 127.0.0.1 --port 4000`，`NODE_ENV=production`，禁用遥测，`--max-old-space-size=768` |
| 启动及恢复 | 三个独立业务 launchd job；网站 `RunAtLoad=true`、`KeepAlive=true`、`ThrottleInterval=30`、`ProcessType=Background`、`Nice=5`；三项 ready 均 200 |
| 资源 | 网站、两个 Worker、私有子进程和原 Tunnel 合计 RSS 快照约 **181.0 MiB**；不是峰值或长期压测 |
| 日志 | 六个网站/Worker日志均 0600，未发现三个内部方向凭据值；未公开原始日志或私密配置 |

公网验收使用原正常 Chrome 管理员会话、一次性普通用户无痕窗口，以及新访客窗口分别验证：

1. 原 `admin` 保持有效，认证、Projects、Hunter、Tracking 读取全部 200；原主页项目 1 条、猎手信号 1 条，Tracking 订阅和推文均为 0，没有在公网写入业务种子。
2. 管理员及普通用户“启用本页语音”均关闭，显示“语音已关闭”。普通用户可见个人语音控件，业务抽屉显示“只读视图”；未启用实际扬声。
3. 普通用户五项 GET 返回 200；携带有效 CSRF 的 Tracking POST/PATCH/DELETE 均返回 403。
4. 临时账号 `c0_voice_viewer_1792120001` 经原 CLI 禁用后，已经认证打开的 SSE 正常 EOF，只有一个 heartbeat、零业务事件、无流错误。从建立到结束约 15.4 秒，包含禁用前准备时间，不作为撤销延迟 SLA。
5. 禁用后认证、Projects、Hunter、Tracking 四项 GET 均返回 401；原管理员再次读取仍为 200。临时口令已从精确测试文件移除，账号没有删除或重新启用；旧 B4 和两个 B3 临时账号也保持禁用。
6. 新访客访问 v2 后进入 `dash.cloudflare.com/login` 的 Cloudflare 登录页面，应用不可见；未尝试登录验证或绕过门禁。不带 Cookie 的首页、Tracking、订阅 API、SSE 四次 HTTPS 请求均 TLS 验证成功，由 Cloudflare 返回 403。

浏览器窗口初期原生焦点陈旧，重新选择应用并核验新状态后完成登录；未读取真实管理员口令。第一次控制台 SSE 解析器因正则转义出现语法错误，尚未 fetch；改用逐行解析后建立一次验收流并取得上述回执。最终生产参数审计最初假设存在 HOSTNAME 环境键而失败；实际启动器显式绑定 loopback，修正审计读法后通过，未修改运行配置。

来源沿用已验语音库 `684d4013d97118612cdfbdc77d32adfc22704af8` / 控制提交 `6f6ba3c4e5ca0fcea4b98873faf340da64082eac`，接线提交 `5e32a35663036997812ebe8c758220f885015b0a`。仅接收库 16 路径增量；网站四份接线复用既有唯一 EventSource、真实 B1 actor/epoch，metadata 只查既有订阅和 Projects 只读接口，校验 envelope、真实 ID、正 revision，按超时和撤销取消。没有新业务库或第二条流。原 77 来源检查、B3 原 62 来源及精确 preflight 例外、B4/C03、8 份主页冻结检查保留；实际旧哈希保持数逐项计算为 70。两份冻结 Worker compiled 哈希不变，没有重建它们。

本地同一正式构建此前通过 **48 项无声生产浏览器检查、12 项 metadata 测试、32 项原语音库测试**，UI/Next build 和网站 typecheck 通过；本轮复核原回执、测试脚本及四张最终截图哈希后部署，没有把既有或重复测试累计为新增数量。本地时间、Speech、SSE 帧使用浏览器替身，真实 B1、独立订阅/Projects metadata 与服务生命周期确实运行。1440/390 两角色最终截图在不可变 `run-1792095246818597000/`；首批重绘缺陷及两次回执继续保留，不算 96。此前 B3 的 76 项离线集成断言见 [B3 报告](./B3-ACCEPTANCE.md)，本轮未重跑，也不作为真实 WSS 证明。原库首次根目录测试缺 TSX 配置，纠正 loader 后原 32 项通过，没有因此修改库或重复构建。

公网证据另存不可变 `public-run-1792131265215463000/`，含脱敏 API 回执、两角色关闭状态及截图、门禁、运行审计、备份清单，逐文件 hash 见 [voice-acceptance.json](./voice-acceptance.json)。公网总回执 SHA256 为 `386c83acaab4102abbb2f2fed35d3e6b90435528b11d222b48a23175d6e9c4fe`；运行审计副本 SHA256 为 `1c781704ae4e0741254a7ffcc91368322c248b05eb534ab47de4f4b40fb5543d`。原本地截图未覆盖。B3 历史 fixed latest-audit 指针曾被后续只读审计更新，其原历史 hash 与限制已保留在 `historical_preapproval`；不声称该指针仍保存原快照字节。

运行根目录 `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite`；四库仍在原 `data/{auth,projects,hunter,tracking}/`。日常使用现有公网入口及 launchd 管理，不从工作区启动第二个网站。只读查看可用 `launchctl print gui/$(id -u)/ca.ikun.v2.c0lite.web`，不要原样公开输出，其中可能包含私密环境参数。

回滚副本完整保留在：

`/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/rollbacks/64088893841122491aba508fdb514507db3d9339-20261016-140458`

需要回滚时，先核对归属、当前 SHA 并另作四库在线备份；仅 bootout 新 v2 web label，恢复该快照的 web plist、web env、owner，bootstrap 同一 web label，再核对旧 release `64088893841122491aba508fdb514507db3d9339` / build `QTLRQ2vGatyCJCEhtFEVA`、三项 ready、两个 Worker 原 PID/配置。保持当前数据路径，不把备份写回四库，不停止 Worker/Tunnel；回滚 receipt 另存。升级器 ready 失败分支已有此恢复机制，本轮升级成功，**未触发或执行生产回滚，未做 Worker 故障注入**。

剩余边界：真实采集保持关闭，未调用 6551、REST、付费 API 或共享 Watch；未验收实际听感和真实推文扬声。既有 `/internal/v1/ingest/tracking` 仍为 **501**；冻结 Tracking 无 delivery/claim/ACK loop，pending 不代表送达或完整状态闭环。猎手发现→人工加入→接收真实推文→主页展示的真实来源全链路尚未验收。本轮未收件后续 Projects delta，未切换 `ikun.ca`，main 仍为 `63e8a2857241c6a76226f21435e40db9736a1e7e`。

机器报告：[voice-acceptance.json](./voice-acceptance.json)。来源：[voice-source-binding.json](./voice-source-binding.json)；本地验收：[voice-local-acceptance.json](./voice-local-acceptance.json)；构建证据：[voice-build-evidence.json](./voice-build-evidence.json)。
