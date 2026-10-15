# B3 Tracking 交接（待总管冻结与正式接线）

权威：579a57f2e3e470525eb53f9f1f85ba75d25f3728，认证审查967f3098e84de7e299d970019d56b571ac63de94，C03冻结审查0e2c86f3c00e03bcc7e9c49a5572f182d4c86b8a。B1固定f097bd4722155d5e689b8894956391ed7e5f2fa7，B2固定aa51a640a159e4c8f6cdd841a25f4279e73075ba（继承cc95认证修复）。不合入协调分支。

当前实现：published-v1显式profile；服务端全量S/A/B筛选/计数/排序/分页；跨代稳定活动、独立QUOTE/结构分类、15天保留/永久小账本、验证备份/显式恢复。旧默认latest/activities保留字段和方向。真实来源关闭；只有私有本地夹具验收，未合并/推送/部署。

候选源码提交：c4de379a67bd9b154bab87ce81d4645b53102ea0；最小游标取消修复提交69f2609845ad751f46bc17a5cc060bb9122f9c3a。`59e5286f605313b20a3ec0c7e976341f3ee6104e`的完整验收另存NIGHT-EVIDENCE-59e5286.json及对应manifest，包含131个pytest、真实Next六类303/401与五类静默SSE撤销、原生429、1440/390共15组完整浏览器流程。该旧版通过不冒充当前源码的全量浏览器验收。当前131个pytest通过（2个wrapper内部9+12=21个Node项不重复累加），新生产Next六类303/401、五类静默SSE撤销、原生429通过；新1440/390定向feed共6组通过，最终截图已查看。62个源码输入、349个运行输入、135个compiled文件、产物及锁回执见NIGHT-EVIDENCE.json和NIGHT-SOURCE-MANIFEST.json。构建后仅定向浏览器脚本readiness/截图等待改变，349个运行输入逐字节一致，未重复全构建。

游标取消修复仅改变自有BFF：错误正文超过64KiB或提前读取失败时取消reader，再释放锁；所有分支finally中止总controller。正常429先完整缓冲再返回，避免取消尚未消费的响应正文。新增三项回归先在旧实现复现失败，再验证超限取消、提前失败取消、延迟游标429正文及Retry-After保留。Python/业务SQL/权限/评分协议不改。

资源约束：本夜项目总管已解除此前完整构建/Chrome暂停，统一使用唯一主锁，集成优先。本P2按总管要求仅重做生产build/bind、实际Next429及关键feed浏览器回归；测试脚本单独调整且运行字节不变时，只在锁内复跑该定向浏览器，不重复全构建。语音仍由UI在总管冻结核心后接手。

R1：目标新路径的第一次身份提交即ready=0；最新ledger合并、清理及完整性验证后才ready=1。复制、inactivate、ledger、cleanup、activation前的中断均应拒绝启动；恢复后旧SSE锚点422，不将恢复包自身作为当前ledger来源。需要独立当前库（停止源worker）或更新且单独验证的备份，以及外部已知expected watermark。无法证明去重水位时拒绝恢复，不宣称任意丢盘零RPO。

R2：retention_now使用单条UPDATE MAX RETURNING，所有autocommit GET/SSE也原子单调；回拨不复活。异常时钟持久标记，物理清理停止，clock-check显式确认只允许非回退时间。

R3：评分批并发≤2；每attempt取消并等待旧批收敛后才重取，单lookup≤2秒、总feed≤8秒；任何源失败无items/total/cursor。实际B1/Projects UDS联验与合成取消预算夹具分别记，不冒充真实provider验收。

## 运行与迁移（由集成按冻结来源接收后执行）

Runtime仅使用独立release，不能从Worktree或.b3/preview运行。Node24 compiled `services/tracking-worker/dist/main.js` 由已有 `scripts/service.mjs tracking start`启动；Python3.11+固定requirements.lock.txt，绝对 `services/tracking-worker/python/entry.py`从其release源码导入，不依赖当前cwd或开发editable安装。Node子进程cwd为私有配置目录，强制IKUN_TRACKING_EXTERNAL_IO_DISABLED=1，裁剪环境，不继承provider凭据；真实外采配置冲突直接拒绝启动。launchd本身WorkingDirectory为私有job cwd，不能有.env文件。示例plist未安装。

以下ABS均由集成替换为独立release/私有DataRoot，service_token_file为自己的0600方向凭据，不能发到聊天。配置0600、job cwd0700；remote_enabled=false、dedicated_account=false、token_file空。方向API仍可受理受控内部commands/观察回执，不代表已接真实来源。

```sh
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py init --config /ABS_PRIVATE_JOB_CWD/tracking.json
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py migrate --config /ABS_PRIVATE_JOB_CWD/tracking.json
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/integration/preflight-release.py --release-root /ABS_RELEASE --job-cwd /ABS_PRIVATE_JOB_CWD --config /ABS_PRIVATE_JOB_CWD/tracking.json
```

init/migrate是唯一DDL入口。v3升级先成功备份再事务迁移004；001—003原字节不改。普通serve/API/ready不运行迁移。新库生成本库私有cursor密钥，不复用任何服务/provider凭据。

```sh
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py restore --config /ABS_NEW_PRIVATE_JOB_CWD/tracking.json --backup /ABS_DATA/tracking/backups/VERIFIED_JOB --ledger-source /ABS_CURRENT_DATA/tracking/tracking.db --expected-watermark KNOWN_NONREGRESSING_INTEGER
/ABS_RELEASE/services/tracking-worker/python/.venv/bin/python /ABS_RELEASE/services/tracking-worker/python/entry.py clock-check --config /ABS_PRIVATE_JOB_CWD/tracking.json --acknowledge-clock
```

恢复只向不存在的新路径写入；source必须本Tracking库或独立已验证更新备份，禁止跨库SQL/ATTACH。clock确认不是通用绕过开关，UTC仍小于已持久高水位时拒绝。失败目标保持inactive供诊断，不能当正常库启动。

启动：在无.env的私有job cwd，设置DATA_ROOT、IKUN_TRACKING_CONFIG、IKUN_TRACKING_PYTHON后运行绝对Node与绝对scripts/service.mjs。平台外采关闭标记在health/ready与internal/status均可查；页面明确“未连接真实来源”。测试站如有夹具数据，网站须另设IKUN_TRACKING_FIXTURE=1显示“本地验收夹具”。不要将fixture入口或测试脚本映射到正式API。

## 接线与边界

候选BFF/page/Action/controller全部位于自有integration/website，正式路径去掉该前缀映射到apps/website；tracking-live.patch只应用到固定Tracking UI d90598f4bc595458ce26c5ee1c2e1618e318abc0，不改CSS。所有人类请求由真实B1 guard验证，superadmin写、user只读；CSRF/If-Match/幂等不变。GET /api/v1/tracking/latest?profile=published-v1由BFF经既有Projects IPC评级，并将投影送本Worker；Worker不持有Projects凭据，不接触其库。SSE候选 `/api/v1/events/stream`仅Tracking流，统一多源组合由集成owner完成，不能覆盖其他来源。

语音未实施。可供后续addon消费的已审基础：SSE tracking.feed.activity.created.v1的稳定event_id/activity_id/subscription_id、is_live_new/replay；初连与Last-Event-ID历史帧强制replay。真实notes与S/A/B来自该活动在published-v1投影的权威结果；订阅备注空或评分非S/A/B不播。UI owner在B3冻结后按总管门禁接手，本模块未加入播放器、开关或队列。

B2 ingest/tracking仍501，outbox仅pending/可查询，过期正文清除后为expired_pending_reconciliation，不伪造投递成功；commands、审计和最小去重账本保留。实际6551/付费/共享Watch/跨worker公网/生产新作业与域名接线未执行，正式接收由总管/集成负责。NIGHT-EVIDENCE.json记录source SHA、精确映射、SQL/锁/入口hash与实际回执；只证明本地隔离候选，不证明线上接线。

补充：恢复前先用entry.py status读取已知ledger_high_water，停源worker后以外部已知非退回水位执行恢复；entry.py backup创建新的成功验证副本。若旧包与当前projects/commands/public_receipts/receipts/audit控制状态不同，拒绝恢复旧包，先刷新备份，避免覆盖人工备注或恢复旧命令。

正式SSE接线遵循8b84ee97a94bae28e98b550b2721991f30088486：候选/app/api/v1/events/stream/route.ts处理函数由集成映射到正式/api/v1/tracking/events，controller EventSource URL做精确alias补丁；保留原Projects全局SSE，不覆盖。该接线由集成owner在核心freeze后执行，本候选不为alias重复重建。

## feed-query-view-v1（6ea8b004c368e17a123e055848f59f6370f2c29d已批准）

published-v1可选X-Tracking-Query-View:qv1_UUIDv4；BFF严格校验后仅传bases/pages的query_view_id。非null时只回收同actor_hash+view的缓存，页请求不回收；其他标签/用户、无hint旧客户端不变。无hint仍受全站8槽配额，第9个活跃查询429。两张现有缓存表仅加nullable列，不加新表/DB/service/token。带hint的签名cursor加入w，无hint保持原形状；主动刷新撤销本视图旧cursor(409)/basis(404)，不续期旧查询。controller每次挂载用useRef保存新UUID，历史versioned重放不刷新，live SSE合并250ms。所有版本/2秒8秒/并发2/60秒/64MiB门禁保持。
