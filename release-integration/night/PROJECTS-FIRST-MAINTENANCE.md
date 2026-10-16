# Projects 首批准确维护执行包

状态：**READY_FOR_ROOT_EXACT_REVIEW_NOT_EXECUTED**。最新直接人类授权 `01a143aa-3791-7732-9065-410adf6e08f2` 及 `01a1443e-2647-7f63-bb04-7473cd52e1fd` 明确受控迁移并继续推进；06:02 的误发更正属于更早语音批次。旧端停止已验收，不再执行旧 operator。当前交付尚未停止 v2、连接运行库、备份运行库或实际导入；root 审准确 Git SHA/计划/命令后再执行，不向用户重复索取迁移授权。

| 绑定 | 准确值 |
| --- | --- |
| 原 Projects CLI | `09afbcfd7ba7d809750d4b27c7599c952335b35f`；44 个 Git 文件暂存独立 0700/0600 目录，非运行 release |
| 正式输入 | `5afc6a274db8a1ec162a43660db8b5ee24a5058074afbd6f308bd32e302cec7e`；32 项目、1412 隔离、40 排除，1484 条闭合 |
| 决策 / 最终源 | `79a3bb0b2d6177842c15ed0aa1461a1eb1c2056754085cd0d429409da0f98388` / `8f5a453a705dbe0ba4c3957c94098ba05684a95b1ef54ca16243fa90aa8fac1f` |
| PG 来源归档 | `d0e25f6472aca37ff408ff4ff8219fb6953ab698e053add40dc14e7f44431d46`；与 manifest hash 分开 |
| 已验复制库演练 | `5364810e3dcdc79790781cc7539dbfbe295facfaa98460cc5138cb4377f21ffd`；仅演练，不给 Worker 使用演练 ID |
| 操作工具 SHA256 | `6d594df36f3067609a607f78161b32084fef1b38e72c7126f647d8014268898c` |
| 最终只读 plan | `.runtime/v2-maintenance/projects-first/09af-5afc-v1/execution-plan-v3.json`，SHA256 `cf75f9ca903ae4168eadbd9df6cd7f2e066cf8cbe1dd10b3b4a3c08ff27a21c1` |
| 32 项夹具回执 | `.runtime/v2-maintenance/projects-first-tests/run-1792149523491786000/receipt.json`，SHA256 `e13e4e561586d2b6596a072ca8ba5648339cfc18284536f6e46d610832701f4e` |
| 真实只读 status | `.runtime/v2-maintenance/projects-first/09af-5afc-v1/readonly-status-v3-before-execution.json`，SHA256 `e66cc3e9344ae4167d1eeb1564693a23805d6c81701fc07c247eddb32b5a5b72`；not_started、web87924、动作/活库连接均0、journal未写 |

本页相对路径均以 `/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/` 为根。v1/v2 plan 保留，但被最终工具指纹取代，不再作为执行输入。

## 操作顺序与唯一 writer

仅 `ca.ikun.v2.c0lite.web` 及其已登记 Next/Projects IPC 树短停；当前树为 87924、87976、87978、87986、87987，原 socket `/private/tmp/ikp-R8jWuG/p.sock`。原网站 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb` / BUILD `X0CYNNjMlhJWNcjEpx1PF` 保持，331 源码/271 构建逐项校验，不收新网站源码、不构建 Next。

1. 核准准确 clean Git、main 未变、工具及两份复用 helper、44 个 CLI 文件、解释器、正式输入/决策/manifest/演练及全部引用资产、网站配置/源码/构建。原保护 guard 只排除获准重启的 v2_web，另七个进程与保护文件/四库 inode 继续守卫。两 Worker ready200 且外采 false。
2. 每个维护窗口新建 `before_online_N` 四库在线备份；SQLite Online Backup API 后封存**目的副本**，integrity/FK/hash 通过。两个 Worker 仍运行，因此四份备份分别一致，不宣称四库同一事务时刻。
3. 再核 web PID/start/cwd/全部已审子身份，保存 `stop_intent` 和子树，二次检查保护后代，再只 bootout 固定 web label 一次。等原 PID/start 全退；重新托管到其他父进程但仍同 start 的子进程不算退出。Auth/Projects DB、WAL、SHM 无 RW holder；4000 无 listener、原 socket 无 holder。未知 writer/端口查询失败均阻断。
4. 新建 `stopped_window_N` 四库备份。仅用停止窗口的 Auth/Projects 副本计算带类型、含重复次数的行指纹；Auth schema2/application_id 与 Projects schema2/application_id 必须正确。首次实际 Projects 必须与已验演练原库 13 表种子完全相同；有人工变更就恢复网站并另做新演练，不覆盖人工字段。
5. 唯一原 CLI `python -m projects_service.takeover` 默认 dry-run 先核 32/32/1/1412/1444 计划计数。实际 apply 仅增加 `--apply --writer-stopped --mapping`；使用原 projects.db/inode，不执行新 SQL、不迁 Auth、不操作其他库业务行。子环境白名单、固定 PYTHONPATH、禁 user-site/字节缓存，没有 provider token。
6. 新建 `after_import_N` 四库备份；Auth 所有表逐行相同，原项目所有人工字段/revision 与所有原行保留，只有 projects/project_sources/project_settings 可新增，其他十表精确不变。原 CLI 再次默认只读 dry-run 必须 replayed=true、五个 new 计数0；最小 export 与 owner 持久 receipt 的映射相同。
7. 同一原 plist bootstrap 网站一次，核 ready、原 release cwd、受托管树及新私有 socket；再核七保护身份/Worker hard-off/四库 inode/所有配置与构建。成功后才写最终 receipt 与 journal.migrated_domains=projects；不改变原 operator_steps/旧端完成状态。

本阶段不收 Worker 新源码、不停它们、不执行它们的迁移，不建立真实 WSS 或调用 6551/REST/Watch。Hunter/Tracking 最近修复候选另待准确收件，不能混入这个 Projects-only 包。

## 准确命令与重入

cwd 固定为上列 integration 工作树；解释器 `/Users/lvlei/.local/bin/python3.11`，环境 `PYTHONDONTWRITEBYTECODE=1`。Git 提交后另写私有 `reviewed-execution-command.json`，其中 `candidate` 是本次交付的准确40位 SHA，`argv` 是可直接审核的实际参数数组；其路径与 hash 记最终回复。这样不在同一 Git 提交里自引用尚未生成的提交 SHA。**root 审这一个 candidate/plan/argv 后才执行其 --execute，不取任意 HEAD 代替准确值。**

原 owner 的实际子参数固定：

```text
<plan.python> -m projects_service.takeover
--database /Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/data/projects/projects.db
--package /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/projects/modules/projects/artifacts/formal-input-d0e25f64-79a3bb0b-v1/projects-input-v1.json
--expected-package-sha256 5afc6a274db8a1ec162a43660db8b5ee24a5058074afbd6f308bd32e302cec7e
--receipt <本阶段固定输出目录中的新prequery/postquery文件，apply为projects-apply-receipt.json>
```

apply 另加 `--mapping <固定输出目录>/projects-export.json --apply --writer-stopped`。最终真实 export 与 apply receipt 都在 `.runtime/v2-maintenance/projects-first/09af-5afc-v1/`；尚不存在，不给后续 Worker 传演练文件。

以下命令只读，不连接业务库、不加 journal 锁、不更改 journal、不停启服务；可用于未知 stop_intent 对账：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/lvlei/.local/bin/python3.11 release-integration/scripts/projects_first_maintenance.py --status --plan /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/v2-maintenance/projects-first/09af-5afc-v1/execution-plan-v3.json --plan-sha256 cf75f9ca903ae4168eadbd9df6cd7f2e066cf8cbe1dd10b3b4a3c08ff27a21c1
```

| 中断状态 | 处理和恢复条件 |
| --- | --- |
| bootout 已发，job仍loaded，或原子树未退，或 writer/port/socket fence 不过 | --status 如实保留未知/存活 PID；不强杀、不再发 bootout、不盲目 bootstrap。原进程自然退出且所有 fence 清楚后，同一准确执行命令可 reconcile 原 stop_intent 并继续。状态查询本身不把 stopped 标为成功。 |
| 停止已确认，apply 前失败 | 工具确认四库 inode、网站原文件、Auth/Projects schema2/integrity/FK 与无未知 writer 后，调用现有 restore_web_once；不回写任何备份。 |
| apply 可能已提交、receipt/export 尚未完成 | 保留原包与 import_intent，绝不重造 package/ID。能证明 Auth/Projects 原行安全时恢复同一0ce网站；再次维护须新 --prepare 计划，root 审其新 web PID/start/hash 后，执行同一候选加 `--resume-recovered`。原 owner 只认同包批次，重放/重导原映射；不会生成第二组 canonical。若原行/兼容检查失败，保持网站停止等待 owner/root 处置。 |
| bootstrap 返回未知且job仍卸载 | 不自动重复。已loaded时可核同一0ce cwd、ready、树/socket后对账；仍卸载则等 root 精确审查恢复状态。 |
| 完成后再运行准确命令 | 校验最终回执及其内部每个原备份/export hash 后，返回 ALREADY_COMPLETE_NO_ACTION；不重复停服或导入。 |

唯一恢复底层命令为 `/bin/launchctl bootstrap gui/<当前uid> /Users/lvlei/Library/LaunchAgents/ca.ikun.v2.c0lite.web.plist`，仅由已有 `restore_web_once` 在落盘 restore_intent、job确实卸载、整棵原树已退、fence通过且schema2/数据保护通过后调用。**不要把此命令脱离这些前置单独执行**。没有数据库覆盖式回滚、schema降级、旧端重启、Worker/Tunnel停启或新恢复服务。

## 验证与限制

最终 **32/32 夹具通过**，包含真实临时 SQLite Online Backup/逐行保护，以及模拟 launchd/PID复用/后代重父化/未知停启/重复执行/提交后丢回执恢复/坏原行阻断恢复/只读对账不改 journal。它们不证明已实际停启或导入。首轮29项中1失败4错误是夹具漏 python/code_root；修正夹具后的29项及最终增补的32项分列保留，不累计61。原09af复制库演练另由root独立验收，不将本夹具当新的真实导入证明。

跨窗口回报被自动审批拒绝，原因是该次具体报告未获明确发送授权；没有换工具重试。本地文件及本窗口 final 供总管直接读取，这不是维护动作被拒绝。前段一度误重复已完成的语音只读核验，mode=ro 活库打开失败即退出；没有新部署/账号操作/业务DML，其结果不计入本维护测试或公网证明。
