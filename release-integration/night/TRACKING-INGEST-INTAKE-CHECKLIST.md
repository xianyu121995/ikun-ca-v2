# Tracking 501 后续收件清单（准备稿，尚未收件）

状态 **HELD_IMPLEMENTATION_REVIEW_REQUIRED**。仅准备集成清单；没有接收实现、构建、部署或更改配置。2026-10-16 核对：integration 为 `a2a3658a3f07fae8f297bd00b53a4aced8b17aae`，已部署网站为用户批准的 `19863b2af031fc2592bb6d73b7161efc77b0bd1d`，BUILD_ID `toKW74u9T1cCk_lyTUZXo`；两者仅验收文档有差异。语音批次已经验收冻结，不回退或重复开发。

| 准入项 | 收件前必须取得或核对 |
| --- | --- |
| 协议来源 | 提案 `b5a634ba76df27f67a37bc69f9a39cdba8604151`，总管补正批准 `d7c0093c4dd3c09fc74faa2a44ede073e32bca72`；二者是协议依据，不是已验业务实现 |
| 真正实现来源 | 等待 Projects 原 owner 的完整实现 SHA、基线、逐路径 before/after hash、回归回执，以及总管审查通过的准确控制 SHA；未到齐不 cherry-pick/merge |
| 最小收件范围 | 只选已审 Projects 业务、Node/UDS 接线、协议 MD/JSON、测试及必要来源记录增量；不整体合入 owner 父分支网站历史。实际逐路径白名单须由交付 diff 固定，目前不凭预期文件名放行 |
| 现有触点 | `modules/projects/candidate/projects_service/{transport.py,service.py}`、`modules/projects/integration/website/lib/projects.ts` 及实际站点 `apps/website/lib/projects.ts`；如新增模型/测试/文档文件需逐个列明。既有 ingest/receipt 两个 route 当前只是委托，不因存在就假定必须改 |
| 来源守卫 | 保留原 77/B3 62/B4/C03/主页冻结约束和语音 16 库文件+4接线；对确需更改的接收端路径只建立准确 before→after 例外，不能删除守卫或全局重置旧 hash |
| 协议补正 | owner 前向更新同名协议 MD/JSON 及互相绑定 hash，Tracking ingest HTTP 为 131072 字节，Hunter 仍 65536、IPC 仍 131072；旧提案的 65536 不得直接当最终配置 |
| 内部凭据 | 本机只读确认新站 web env 尚无 `PROJECTS_INGEST_TRACKING_TOKEN`。未来部署 manifest 必须单列“仅新增网站自有私密 env 这一键”；随机独立、至少32字符，不复用 Tracking API/Hunter/IPC/provider 凭据，不在 Git/聊天/日志输出值。当前不生成、不写入，冻结 Worker 配置不动 |
| 运行差异 | 后续只允许新 v2 网站和其既有受托管 Projects IPC；网站更换 candidate/build，两 Worker 的原 release/source/PID/plan/env/plist/config/data 保持原位。没有新的后台发送器、定时器或 Worker API |

接收端本地验收必须覆盖下列范围，使用独立四库、实际 Node HTTP/UDS 与合成原始 envelope：

1. 严格只接收 `tracking.feed.activity.created.v1` / `tracking.feed.activity.updated.v1`；十字段 envelope、十五字段 payload、固定 UUIDv5、真实 canonical/sub alias、原字符串与时间表示的 canonical SHA256。created 的原创/引用、WSS/live/non-replay 约束与 updated 的补全/可见性语义分别验证。
2. 独立 Tracking 方向凭据；无/错 token、Cookie 单独、伪造角色头均不授权；错 source/scope、非法或未知字段、非有限数、坏 URL/ID/hash 按批准协议拒绝。绕过 Proxy 的真实 handler/IPC 入口同样校验。
3. 两种事件首次受理、同 ID/hash 幂等返回原 receipt、异 hash 409；并发一条回执、别名映射冲突、无/跨 scope canonical、事务异常全回滚及重启后可查。
4. `X-Expected-Event-SHA256` 可选，沿原方向授权；格式错422、已存不符409、无回执404。Receipt DTO 保持原六字段，不能偷偷新增必填字段或用 hash 代替鉴权。
5. 最大 emoji 和控制字符正文、非法 UTF-8/surrogate、原始超大 HTTP、RPC 包装边界；无截断、无扩大 Hunter/IPC 限额、无重造 hash。总管独立样例 envelope/RPC 分别 81609/81777、121609/121777 字节，需结合实际最终 schema 重验。
6. 丢 ACK 后先 GET 原 ID/hash；原样 scrub 对象 POST422；已有过期回执可 GET；正文已删且404仍 unknown，不从 SSE/缓存重建，不生成新事件 ID、不假 ACK。只确认网站历史受理。
7. 仅在 projects.db 原 `event_inbox` / `project_sources` 留 ID、时间、hash、receipt、关联；不存正文/raw/name/URL副本，不改评级、手工资料、主页成员、revision、命令或公开 SSE，不打开其他领域库。schema/校验和不迁移。
8. 原 Hunter/B2/C03/B1 与已验语音接线回归；测试数量逐套报告，不累计重复和子项。确需正式构建/浏览器时持唯一 heavy lock 串行。源码/构建/测试脚本/证据逐项 hash 绑定，旧证据只读保留。

收到总管实际代码审查通过的准确 SHA 后，先只生成可审集成候选及上述证据。部署是独立步骤：核对候选审批，在线备份四库，记录原 web env/owner/plist/receipt 和两 Worker PID、配置 hash、四库 inode；仅升级网站/Projects IPC，manifest 明确新增私密键和新 build；再验证三 ready、两 Worker 完全保持、B1角色/403/401/Access、临时账号禁用及日志/备份。回滚仅恢复原 web release/env/owner/plist，移除本轮新增配置应通过原 env 快照恢复，不覆盖四库或变更 Worker/Tunnel。

**验收表述固定为“网站受理且可按原 hash reconcile”**。冻结 Tracking 没有 delivery/claim/ACK loop；网站不能读写 tracking.db 或伪造 ACK 清 pending。完整 Worker 本地状态闭环、真实采集、实际听感、正式主域名上线继续单列未验收。此清单没有授权 6551 盘点、停旧版、Watch 变更或真实/付费调用。
