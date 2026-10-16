# Tracking 501 项目紧凑状态（只读交接）

接收端已上线，无需重复开发或部署。冻结Projects业务源 `6067658d6092e4d046a8691e8f2f93b34c717801`；集成收件 `0b0f4549758b74ec5defc06493054f41d80d439d`；实际网站 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb` / BUILD `X0CYNNjMlhJWNcjEpx1PF`；最终交付报告 `fa51e92c66a374b95c5397cd50cdd021ebe1496b`。实际公网收尾时间2026-10-16 15:36:15上海，后续只读维护预检仍核对331源码/271构建匹配、三ready200、两Worker外采false。

原验收：[TRACKING-INGEST-ACCEPTANCE.md](./TRACKING-INGEST-ACCEPTANCE.md)、[tracking-ingest-acceptance.json](./tracking-ingest-acceptance.json)。私密不可变公网证据目录：`release-integration/.runtime/tracking-ingest/public-evidence-1792136175415559000/`，总回执SHA256 `d41b93500af1d4cd69fcaac8abdc51b39ba0e27054ab14ba39e2825da46bd1fd`；独立运行审计、升级/备份及各附件hash在机器报告中，不公开凭据。

实际接收端无副作用探针：无凭据401、错方向401、错scope403、有效方向空对象422、未知receipt404，已不再返回501；公网合法观察POST为0。真实管理员与普通用户读权限/写403、禁用401及静默SSE撤销均已验，临时账号已禁用。正式Next/UDS隔离套件108项已覆盖持久幂等、异hash409、原hash查询reconcile、丢ACK、重启恢复及故障回滚；它是合成来源，不能当真实采集证明。

边界仍在：冻结Tracking来源c4de及其运行版本6408889没有delivery/claim/ACK/reconcile publisher回写任务。接收端“可受理并按原hash查询”不等于tracking.db pending已送达。过期receipt404仍为unknown，不能重建正文、换ID重投或伪造ACK。完整pending/expired/TTL闭环须Tracking原owner另审；本501网站批次没有修改Worker。后来70c1迁移/adopt-only已独立验收，仍不等于publisher闭环通过；当前未审样本/quote增量不自动收件。

本501实际升级走原入口通过，没有自动审批拒绝或换入口重试。历史语音激活曾因缺直接授权被拒，之后用户明确批准19863而完成；那是另一批次，不作为本项部署阻断或本项已触发拒绝的证据。

当前工作是分批迁移的工具/隔离演练准备，不重部署0ce、不切主域名、不改Cloudflare、不启真实6551。首批仅Projects网站短维护尚未执行；Worker仍原进程/配置。旧侧停止是后来的独立授权范围，不能与501网站升级混算。
