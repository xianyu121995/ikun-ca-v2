# 精确旧侧操作工具待审

状态：`PENDING_ROOT_REVIEW_DRILL_POLICY_DEPENDENCIES`。f517f4b 经控制 885b08f 放行后完成七库及文件归档，PG 读取角色不足而停下；4eb37cf 经控制 74b6327 放行后成功完整 dump，但新演练集群因 POLICY 引用角色缺失而停止恢复。两 job/6466 均未停止，没有迁移或平台调用。直接人类授权为总管 turn `01a143aa-3744-7933-98b1-925db1af2681` 的两条用户消息 `01a143aa-3791-7732-9065-410adf6e08f2`、`01a143c4-70e8-7011-8651-1e20179584f7`；原唯一执行者及 journal 不变。

仅处理 `ca.ikun.overload-tracking`、`com.lvlei.ikun-auto-research` 和复核后 PID 6466 的一次 SIGTERM。顺序为七库备份、私密配置及现存源码归档、只读 PostgreSQL 一致 dump 与独立恢复演练，再精确停获批目标，最后重复快照及演练。每次停止前递归校验原备份资产，不以 receipt 本身替代资产；保护 Alpha、旧 PostgreSQL/监督进程/Tunnel 和 v2 全部进程、配置及四库身份。父 login 6465 不发送信号，但可能自然退出。

SQLite 仅在新副本上封存 DELETE journal，无 WAL/SHM；唯一静态克隆例外是旧 dispatch 的无侧文件稳定校验。备份有时限，失败及 partial 保留。PostgreSQL 密码只进私密子进程环境；新演练集群使用私有 Unix socket，核验 data_directory/端口/PID 后才能 restore 或停止。完整私密备份含非迁移范围数据，不能直接作为导入许可。AI 任务现存入口缺失，仅保存已有文件及缺失事实，不能承诺原样恢复。

实际运行须总管精确 Git 导出复验放行，使用本提交完整 SHA：

```sh
/Users/lvlei/Documents/Codex/2026-10-11/codex-web3-workspace-codex-web3-next/outputs/web3-workspace/backend/.venv/bin/python release-integration/scripts/takeover_operator.py --execute --candidate <本提交完整SHA>
```

失败即留 `release-integration/.runtime/takeover-execution/IKUN-ONLY-2026-10-16/failure-summary.json`，不强杀、不扩大 PID、不自动重发未知结果停止。重复运行仅按 journal 对账；原始进程是否消失仅凭 PID/启动时间，停止前仍严格校验完整身份。自动审批若拒绝，原命令/原因交回，不换入口执行。

最终隔离测试 **30/30**，包含两个全新 PostgreSQL 夹具的真实 dump/decode/restore、SQLite WAL/超时/损坏备份、未知停止结果、执行锁、保护进程树和父 PID 变化；旧服务动作、旧库连接、平台请求均为 0。私密回执 `release-integration/.runtime/takeover-operator-tests/run-1792140975446648000/receipt.json`，SHA256 `865459e5967978e761399eecf6a6bd512ae48a97dcf13e51ef0ec9410c6d8a25`。前期 28 项失败与后续 28/29 项记录均保留，不累计计数；首轮缺 pg_restore 显式 dbname 及空 pgpass 已修复。此次 plan 只读捕获在沙箱内被 ps EPERM 阻止，同一只读捕获获准在本机完成，没有执行停止命令。

另一次语音只读复查发现无 WAL/SHM 时 v2 Projects/Tracking 的 mode=ro 打开失败；原 12 份备份哈希及 integrity/FK 已重验。本工具若遇到同样情况会在停服前失败关闭，不对这些活库使用 immutable 或扩展静态克隆例外。语音原报告及两次私密复查失败回执保留，未重复部署。

## PG 失败及最小修订

f517f4b 的模块角色无全表 SELECT，lvlei 无自身口令，故 `PG_FULL_BACKUP_READONLY_ROLE_UNAVAILABLE`；准确原命令获本机权限，没有自动审批拒绝。原 7 份 SQLite 均 integrity/FK 通过、DELETE 封存，连同文件归档共 25 份原资产 hash 重验；失败后 8 保护进程及批准目标身份仍保持，Alpha 正常。现场全部保留于 `.runtime/takeover-execution/IKUN-ONLY-2026-10-16/`，旧 intent 尚无 dump。

总管指定既有 `LIVE/.runtime/ikun-first-release/original-site/.env`，SHA256 `247dae0379223121c305cc2ba4ad93986df2c4e54df5abd752a0cf3be07e9f70`。只提取唯一 DATABASE_URL，不 source/eval、不加载其他键；校验 uid/0600/单链接/无路径别名及 hash，必须同 module/import 库和 endpoint，精确 web3 角色且口令存在。一次真实只读探测通过：100 表 SELECT 及序列权限完整、active RLS=false；probe 回执 SHA256 `8d2ac3eccb413de6906366bf126adbfd438a45672890854a7c9ba8d52e0030b9`。不创建角色、不 GRANT、不改旧配置。

新选择器只尝试原配置角色和该固定既有角色，均默认及显式 READ ONLY；不再尝试无口令 lvlei。新增来源进入 plan/protected 文件 hash 绑定。恢复执行将先递归复验并复用原 7 库/25 资产，仅继续未完成 PG intent，不覆盖历史失败。修订后完整隔离测试 **35/35**（含原 30，不累计），只测试夹具、无旧库连接；新 5 项覆盖来源 URL 编码、同库约束、hash/alias/权限、重复键、两角色只读及不足权限拒绝。回执 `release-integration/.runtime/takeover-operator-tests/run-1792141730666211000/receipt.json`，SHA256 `50286eac4ab991a514a69e95a6b33137ed9cee5f4a351b42787a5653e7544403`。待新精确提交复审后才恢复原入口。

## 新演练集群 POLICY 依赖修订

既有完整 dump（1,897,368 bytes）SHA256 `7280b1d5c3ea1cd6c75745ca8092b3d4e6e18ce540e499ffa2288044aea3470f`，decoded SQL SHA256 `8ca7aac0d69785c294e101c20b90553d1fc367e13466a7693db95516d848b769`；4 原资产已复核，100 表一致计数保留。只读离线核对 260 条 POLICY、8 个已批准非 PUBLIC 角色；固定白名单在 plan 和工具中逐项比对，未知角色/语法或计数变化失败关闭。初次离线读法遗漏 pg_dump 默认 PUBLIC 省略 TO 的形式，尚未执行恢复；补正并加入独立场景后实际 dump 离线检查通过，未重 dump。

仅在独立 socket/data/PID 守卫通过的新集群创建 NOLOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT/NOREPLICATION/NOBYPASSRLS 占位角色，不复制口令、成员或原权限。明确只验数据恢复，**不声称权限语义复现**；原 archive 的 owner/ACL 保留。唯一允许 reconcile 的既有失败目录、已停止状态 hash 和 archive/decoded hash 均精确固化；要求 stopped=true、无 postmaster.pid，原目录和日志全部保留，journal 记录原现场并另建新 attempt，不删除或覆盖 partial。未审定的失败现场仍拒绝自动重试。

最终完整隔离测试 **39/39**（包含前 35，不累计），真实两临时集群夹具新增 POLICY 引用/最低权限角色恢复，另覆盖默认 PUBLIC、未知依赖、旧端创建角色拒绝、未停止现场拒绝和精确新 attempt 对账。回执 `release-integration/.runtime/takeover-operator-tests/run-1792142533429096000/receipt.json`，SHA256 `6ebd1cda810f4956c6fa0ce31c4f9a10292a5a0696634c2ce5d7c954d8868e5b`。先前 38 项中间回执保留；本修订未恢复生产操作，待准确新 SHA 复审。
