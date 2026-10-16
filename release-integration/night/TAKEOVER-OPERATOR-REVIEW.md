# 精确旧侧操作工具待审

状态：`PENDING_ROOT_REVIEW`，尚未运行 `--execute`，尚未备份或停止旧服务、连接旧 PostgreSQL、迁移或调用平台。直接人类授权为总管 turn `01a143aa-3744-7933-98b1-925db1af2681` 的两条用户消息 `01a143aa-3791-7732-9065-410adf6e08f2`、`01a143c4-70e8-7011-8651-1e20179584f7`；原唯一执行者及 journal 不变。

仅处理 `ca.ikun.overload-tracking`、`com.lvlei.ikun-auto-research` 和复核后 PID 6466 的一次 SIGTERM。顺序为七库备份、私密配置及现存源码归档、只读 PostgreSQL 一致 dump 与独立恢复演练，再精确停获批目标，最后重复快照及演练。每次停止前递归校验原备份资产，不以 receipt 本身替代资产；保护 Alpha、旧 PostgreSQL/监督进程/Tunnel 和 v2 全部进程、配置及四库身份。父 login 6465 不发送信号，但可能自然退出。

SQLite 仅在新副本上封存 DELETE journal，无 WAL/SHM；唯一静态克隆例外是旧 dispatch 的无侧文件稳定校验。备份有时限，失败及 partial 保留。PostgreSQL 密码只进私密子进程环境；新演练集群使用私有 Unix socket，核验 data_directory/端口/PID 后才能 restore 或停止。完整私密备份含非迁移范围数据，不能直接作为导入许可。AI 任务现存入口缺失，仅保存已有文件及缺失事实，不能承诺原样恢复。

实际运行须总管精确 Git 导出复验放行，使用本提交完整 SHA：

```sh
/Users/lvlei/Documents/Codex/2026-10-11/codex-web3-workspace-codex-web3-next/outputs/web3-workspace/backend/.venv/bin/python release-integration/scripts/takeover_operator.py --execute --candidate <本提交完整SHA>
```

失败即留 `release-integration/.runtime/takeover-execution/IKUN-ONLY-2026-10-16/failure-summary.json`，不强杀、不扩大 PID、不自动重发未知结果停止。重复运行仅按 journal 对账；原始进程是否消失仅凭 PID/启动时间，停止前仍严格校验完整身份。自动审批若拒绝，原命令/原因交回，不换入口执行。

最终隔离测试 **30/30**，包含两个全新 PostgreSQL 夹具的真实 dump/decode/restore、SQLite WAL/超时/损坏备份、未知停止结果、执行锁、保护进程树和父 PID 变化；旧服务动作、旧库连接、平台请求均为 0。私密回执 `release-integration/.runtime/takeover-operator-tests/run-1792140975446648000/receipt.json`，SHA256 `865459e5967978e761399eecf6a6bd512ae48a97dcf13e51ef0ec9410c6d8a25`。前期 28 项失败与后续 28/29 项记录均保留，不累计计数；首轮缺 pg_restore 显式 dbname 及空 pgpass 已修复。此次 plan 只读捕获在沙箱内被 ps EPERM 阻止，同一只读捕获获准在本机完成，没有执行停止命令。

另一次语音只读复查发现无 WAL/SHM 时 v2 Projects/Tracking 的 mode=ro 打开失败；原 12 份备份哈希及 integrity/FK 已重验。本工具若遇到同样情况会在停服前失败关闭，不对这些活库使用 immutable 或扩展静态克隆例外。语音原报告及两次私密复查失败回执保留，未重复部署。
