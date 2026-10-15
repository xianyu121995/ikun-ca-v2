# C-03 已批准精确 wire 与 Projects 实现候选

批准依据：`579a57f2e3e470525eb53f9f1f85ba75d25f3728` 的 NIGHT-RELEASE，B3 `4e0b293901c72df0c28180eb849a2d67d8c9c4c9` 提案§6/7。本增量取代 `product-c02-c03-v1` 原稿中 C-03 的回调 HTTP、新方向 token、另一公开 feed 路径和 pending_alignment；原稿保留历史原文/哈希。C-02原有完成/恢复/普通membership/DELETE语义获批，继续复用，无新CRUD。

认证修复祖先为 `cc95dc27852d056457ca0582cff64a88c0eab1d4`，总管有效依赖批准记录为 `967f3098e84de7e299d970019d56b571ac63de94`。本轮不再包装另一认证实例，不改Auth源码或策略。以下是本域实现候选，不冒充B3复合feed或实际Next验收。

## 数据流与权限

浏览器 → BFF当次B1 guard → 既有 ManagedProjectsIpc / `POST /v1/rpc` → Projects。BFF将结果经既有 TRACKING_API_TOKEN 传入B3 bases/snapshots/pages。Worker不取得Projects socket/token，不回调网站评分HTTP，不直接读projects.db，不得到通用写权。没有新服务/端口/公共路径/方向凭据/评分表或迁移。

UDS原方向鉴权、build SHA、0600/0700边界不变。实际user/superadmin均只读；principal必须是网站刚验证的B2 Principal。匿名/强制改密/撤销等在人类入口按既有B1拒绝，域端仍要求principal，拒绝其他role/tenant。浏览器不能提交actor/评分数组冒充BFF；新profile不被公共Projects路由的view参数接纳。

## 精确请求与响应

```json
{"operation":"ratings","contract":"tracking-ratings-v1","request_id":"c03_example","principal":{"user_id":"fixture_user","tenant_id":"ikun-main","role":"user"},"body":{"project_ids":["prj_550e8400-e29b-41d4-a716-446655440000"],"expected_catalog_version":null}}
```

body恰有project_ids和expected_catalog_version。前者为0–200个不同的canonical UUIDv4 ID（不按handle/名称补ID）；空数组取/核验catalog。后者为null或1–128字符字符串；null取得当前版本，空串/过长/非字符串422，非当前版本409 VERSION_CONFLICT。重复/非法/201个ID、未知body字段422；ratings不接受query/target/source/if_match/idempotency_key字段。operation和contract必须成对，不能借该contract选择旧写操作或把ratings放入旧contract。旧Rpc/旧DTO默认语义不变。

data严格为：

```json
{"contract":"tracking-ratings-v1","catalog_version":"opaque_catalog_version","checked_at":"2026-10-16T00:00:00.000Z","items":[{"project_id":"prj_550e8400-e29b-41d4-a716-446655440000","state":"missing","rating":null,"revision":null}]}
```

外层沿用标准data/request_id、X-Request-ID、no-store。items与输入同序，一项不漏不重；每项仅project_id/state/rating/revision。found时rating保持S/A/B/C/D/null全枚举、revision正整数；真实unrated映射null。missing时rating和revision都null，跨scope与不存在一致。主页removed/hidden/completed不删除canonical或清空评分，仍可found。没有名称/备注/来源/credential/raw字段。查询失败不转换为missing或空成功。

checked_at为域端本次读取的真实UTC毫秒时间；B3按批准协议验证不得早于当前15秒/晚于5秒。Tracking本地真实订阅notes及其revision由B3自己的查询取得，不能用Projects.notes/project_name代替。本域不创建第二个备注来源或评分权威。

## 版本与一致性

同一读取事务BEGIN后，取固定scope的project_changes最大已提交sequence（空库0），再取全部请求行。catalog_version为64位hex SHA256的不透明字符串，输入包含contract/scope、域实例随机256bit boot nonce、已有UDS方向凭据摘要及sequence。所有项目变动保守使旧版本失效，重复幂等回放未改变项目不失效；不使用每页指纹或逐项目revision充当全局版本。

每个域实例的nonce在启动生成，不写DB；B0重启、停止后恢复库或轮换UDS方向凭据会产生不同catalog，旧expected返回409。UDS配置为进程生命周期内不可变，凭据轮换经重建受控实例进行；不支持活进程替换DB并保留旧boot。没有新增恢复命令或跨库恢复行为。

跨批必须传相同expected：发生变动则整次调用409、无partial data。SQLite WAL并发写可发生在读取期间，但单次版本与items来自同一快照；下一空批能发现新catalog。B3拥有≤60秒不续期的查询快照、全部候选和监控统计所需ID集合；评分批≤2并发、全部完成后再全量S/A/B筛选计数分页。后续页空批核验和返回前最终核验、limit可变ordinal、用户/查询/政策绑定、notes语义revision以及最多一次只读重取均沿B3提案和根补正，本域不重复实现另一feed或游标。

## 超时与错误

Node既有ipc helper仅对operation=ratings加整个调用2000ms截止，覆盖握手/读取并传播调用者取消；真实上游socket收到abort，不重试。其余既有RPC超时保持原状。配置/存储/传输/坏JSON/错误envelope/超时统一503 UPSTREAM_UNAVAILABLE、无data；已知域端409 VERSION_CONFLICT、422 VALIDATION_ERROR保留。请求错误或旧版本不回退首页，不回退猜测评分。BFF整条feed8秒、basis准备15秒及多批协调归B3实现；没有付费fallback。

Python原IPC严格模型和服务器错误处理复用。域端授权缺principal401、旧用户写入403；错误UDS方向401、错误build403。查询只读，不写operation_receipts/audit/project_changes/inbox/outbox或评分缓存。

## 最小变更与回归

- `transport.py`：增加严格RatingsQuery及成对operation/contract校验；旧业务输入保持原值。
- `ratings.py`：scope内最小四字段投影、catalog及同事务读取；`service.py`仅接入现有READS；`ipc.py`将既有方向身份绑定catalog。
- 自有网站helper只增加ratings的2秒/取消/错误适配，不增加HTTP route或Auth白名单。
- 并发回归发现旧`project_path`对可消失SHM做is_file后再stat的TOCTOU。改为每条路径一次lstat，缺失sidecar容忍，符号/硬链接和非普通文件仍拒绝。此修复服务于两个并发只读批次，不改变CRUD语义。
- `test_tracking_ratings.py`：全评级/缺失、0/1/200/201/重复/非法ID、严格body/profile、两种人类角色、201项目跨批、全局版本变动、完成恢复成员保留、幂等重放、同快照并发写、scope/只开本库/零持久变化、重启恢复/方向轮换和私有实际handler。含一个真实Node UDS传输wrapper。
- `ratings-ipc.test.mjs`：14项真实私有socket传输/严格投影/错误/两秒deadline/取消不重试；B1入口测试新增一项当次真实user principal→UDS→版本冲突；实际B0生命周期原3项增加catalog重启失效断言。Node wrapper计数不与其子项累加。

本地实现测试计数、命令与输入hash另见本轮交付报告/回执。未跑完整Next/Chromium，未声称FeedPageV1全量过滤/统计、B3依赖组合、公网或实际来源已通过。完整build/浏览器如需由相应owner持主仓库唯一heavy lock执行；C03目前没有相关重负载作业。原B2报告/回执/失败现场保留；只改modules/projects，不合并/推送/部署，不改其他Worktree、旧服务、Watch/Tunnel或真实业务数据。
