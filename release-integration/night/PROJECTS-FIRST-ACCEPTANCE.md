# Projects 首批真实迁入验收

状态 **PASS_PROJECTS_FIRST_RUNTIME_IMPORT**。2026-10-16 **19:28:48（上海）**完成。唯一 operator 按准确候选 `4089c9043f36ff8cd5b2c003293bc66f5e5627cf`、工具SHA256 `6d594df36f3067609a607f78161b32084fef1b38e72c7126f647d8014268898c`、原 v3 plan `cf75f9ca903ae4168eadbd9df6cd7f2e066cf8cbe1dd10b3b4a3c08ff27a21c1` 实际执行，exit0。原 Projects owner CLI `09afbcfd7ba7d809750d4b27c7599c952335b35f` 将已审正式包5afc6a27迁入原 projects.db，未重写业务或执行跨库SQL。root `fc537a6` 已独立验收本阶段。

| 检查 | 实际结果 |
| --- | --- |
| 正式项目 | 原1个 → **33个**；新增32个canonical、32来源映射、1个已核验身份别名；1412条隔离，40条排除，1484条来源计数闭合 |
| 原数据保护 | 停止窗口前后Auth全部表逐行相同；原人工项目所有字段/revision及所有原行保留；除projects/project_sources/project_settings允许新增，其他10个Projects表精确不变 |
| 原库身份 | 四库路径/inode/0600/单链接保持；Auth/Projects schema2、Hunter/Tracking schema4；没有覆盖、换库、Auth导入或隐式schema升级 |
| 备份 | before_online_1、stopped_window_1、after_import_1，各4库，共**12份**封存在线备份，hash/integrity/FK通过；双Worker运行，因此不声称四份是同一全局事务时刻 |
| 网站 | 仅ca.ikun.v2.c0lite.web及原受托管Next/Projects IPC短停；PID87924→**54011**，新树54011/54012/54014/54018/54019；新socket `/private/tmp/ikp-aUeczB/p.sock`，0600、holder54014 |
| 网站代码 | 同一 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb` / BUILD `X0CYNNjMlhJWNcjEpx1PF`；331源码/271构建hash匹配，无Next构建或runtime代码修改 |
| 其他进程 | Hunter2608、Tracking25225、v2Tunnel39523及Alpha/旧PG/监督进程/旧Tunnel身份和受保护文件保持；两Worker外采false，未重复旧停服步骤 |
| 同包对账 | 原CLI默认只读dry-run返回replayed=true，五项new计数均0；正式持久export32行与owner回执相同，UUIDv4唯一，和演练ID交集0 |
| 窗口时长 | stop_intent到ready/新树/socket复核恢复为**11.88秒**；这是操作时间区间，不是公网请求中断时长或可用性SLA |

## 正式映射交接

实际输出目录：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/v2-maintenance/projects-first/09af-5afc-v1/`。

- `final-receipt.json`：`bd437fb7dee3c99bf651aa38eede5daa11055c2084f1f068397aa4ef86a715c2`。
- `projects-apply-receipt.json`：`b4ddabddb450c49fb88abf56a88b13f36be5951b032389a52303d98126dff3bf`。
- **`projects-export.json`：`603ed92675b3d116efe118850689dde6c57e6bc55576197ed34da0d74e83463c`**，这是后续唯一真实canonical来源，不使用rehearsal文件。
- `PROJECTS-FIRST-ACTUAL-HANDOFF.json`：`a7c65f0c7bd15a5298006f026bb4b2b2388d6947afd7ee0d093fb2ead99ab741`，另独立复算停止/导入后备份的原行保护和全部引用hash。
- `public-post-import-smoke.json`：`c349aa9044577e17ca8ca8cf915035d4444b411d1ebda370ec89f674e0f3e02f`。

journal保留原operator_steps和旧端完成状态，只新增本维护阶段complete及migrated_domains=[projects]。没有修改原source/plan/待批命令文件。本文为执行后另行报告，不授权在后续HEAD原样重跑旧execute；未来执行仍需对应准确候选和输入。

## 公网与权限收尾

原Chrome管理员刷新Tracking仍有效，语音默认关闭、0订阅/0推文；公网主页显示2个持续跟踪（原B级夹具保留、新增1个S级持续跟踪）、31个其他项目、完成记录0，没有点击业务编辑入口。停止窗口后封存Auth中原5个临时普通账号仍禁用；本阶段没有新建、重新启用或索取用户口令。普通用户读200/写403与撤销401/SSE结束的结论沿此前不可变公网证据，本阶段未重新启用临时账号测试，也不把它记作本批新测试。

三ready均200，双外采false。四条无Cookie HTTPS请求均TLS验证成功，实际跳转到 `cloudflareaccess.com/cdn-cgi/access/login/v2.ikun.ca`，最终200、标题“Sign in ・ Cloudflare Access”，没有应用UI标志；不是应用API200。完整状态、正文hash与最终域名路径见 `http-gate-observations-1792150391707891000.json`，SHA `7cf39296fd89f55d6dfee3049b54f3f5a1024ab4ce7e594249364f2e2073e2b9`，未保存正文或登录challenge参数。没有修改Cloudflare/Access/域名。六份网站/Worker日志权限0600；本阶段没有新增凭据或扫描/公开原始日志内容。

保留验收修正：首个HTTP检查固定断言403而失败；读取真实响应后按“Access登录页200，应用不可见”判定，没有修改运行站或策略。Chrome刷新后一次旧AX元素失效，重新观察并通过地址栏导航完成只读检查，无业务操作。

## 审批与边界

第一次实际exec_command在创建进程前被自动审批拒绝，理由为可信证据未明确批准这次具体停站与真实库迁入；当时只读确认not_started、原PID、journal无本阶段，原拒绝及待批argv完整保留（回执 `d1d76197b5920bc3e5adc8c420d51640d33d04819d546e128d10f18fbcc26f96`）。随后核到总管线程**直接人类消息01a14477-0767-7b41-8866-97b5143a94fa**，明确回答“批准这次网站短停与 Projects 迁入”，问题包含4089/四库备份/32项目/Auth及人工项目保护/恢复原0ce/双Worker和其他边界；原文已封存为 `direct-human-approval-01a14477.json`（`b31ace914371aaabc9553006bf99c7e0ab847daa0dd6714d5bc66f7551839347`）。新增批准后以完全相同的已审入口/argv执行通过，没有换入口绕过拒绝。跨窗口报告发送没有再次尝试，总管直接读取本地证据。

本阶段32项本地运维夹具和root独立32项分列，不累计；Projects原复制库演练仍为独立历史证据。实际迁入结果不替代真实6551来源、Hunter/Tracking接管、投递/ACK闭环、听感、长期压测或整体正式上线验收。没有真实平台调用、新WSS或Watch写；未切ikun.ca、不合main、不push、不重启旧端。

Hunter后续只读收件已核F9准确15Git输入/11原证据，并在工作区ignored私有目录暂存183Git文件；正式目录包90b8/ownership a79c/manifest5e9d匹配。原始暂存因漏umask077触发权限守卫，失败目录保留；新暂存0700/0600，尚未运行离线迁移演练或操作Hunter运行库/服务。此后只准备独立Hunter维护包，固定新兼容reader/原唯一005/schema5备份与hard-off，具体执行另审。

机器摘要：[projects-first-acceptance.json](./projects-first-acceptance.json)。
