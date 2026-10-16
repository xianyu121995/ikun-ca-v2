# 首次样本两读预检（未执行）

Tracking实际迁入报告已提交4d275bf：新增1、旧推文/ledger/通知0、replay0、真实graceful heartbeat0、12备份、固定307d/PID83544恢复硬关。三域迁入完成。

本薄包仅允许0x2a_ikun的 **1次twitter_user_info + 1次完整twitter_watch**，复用当前冻结307d Remote/Config及原F9凭据解析。供应商请求上限2、每次15秒、总执行段35秒、零自动重试；独立计数，不混入后续有限样本预算。不查询余额、创建账号/项目/订阅、写Watch或建WSS，不开运行DB、不启停服务。

候选本机凭据文件存在，来源为原Hunter工程.env；仅统计存在性/权限，真实值和有效性未读取/未验证。前次原字段OPENNEWS_TOKEN不存在，实际0-attempt失败保留。已核原Hunter字段TWITTER_API_TOKEN为6551、API/WSS host匹配，REST另为TWITTERAPI_IO_API_KEY；新版plan显式绑定前者，拒绝REST字段。实际执行才内存映射该明确字段，任何密钥不进argv/日志/报告。请求前后复用当前网站、Hunter78559、Tracking83544、Alpha/PG/Tunnel及文件保护；Alpha重连/健康漂移就停止后续读取。

原response只存0700/0600私有目录。严格稳定userId/handle/实际followers决定WSS或REST；Watch归一化沿原Remote.watches。兼容已核真实顶层data/success/total/usage，顶层及nested总数存在时严格整数==行数，拒绝分页/冲突/重复ID或非bool flags；600计数包含全部Alpha/未知条目。原已验自有Watch ID/flags/组必须精确命中，防止用错6551账号；现有0x2a条目只报告归属、不触碰。结果未知/402/429/超时即保留意图和原回执，不盲重试。

14项本地夹具通过（含原字段别名接线和REST字段拒绝），含原Remote+MockTransport实际两读接线、真实形状top-total、429一次即停及无数据库连接。local-dry-run为0真实请求/0真实凭据读取。旧字段限制和脱敏夹具handle过长的本地失败记录保留；未改冻结业务源。

准确plan与argv在release-integration/.runtime/first-real-sample/readonly-preflight-v1。等待总管准收后才执行。当前不是监听就绪，不能叫人立即发推：拿到身份/名额和现有条目事实后，原有限CLI配置/两域独立writer停启恢复、新Watch最多1次、真实prj/sub及<=300秒证明留到用户待命后生成。Hunter原消费fence不清，REST新号先静默基线；Alpha双DTO观察器仍未运行。
