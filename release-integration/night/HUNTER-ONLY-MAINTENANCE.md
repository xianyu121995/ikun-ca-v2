# Hunter-only 准确维护执行包

状态 **READY_FOR_ROOT_EXACT_REVIEW_NOT_EXECUTED**。仅准备原Hunter独立job维护；没有连接运行库、安装运行文件、停启服务、迁移或外呼。Projects真实迁入已由root fc537a6验收；其32个正式canonical不等于Hunter或Tracking已迁入。两Worker准备/演练的root记录为4378a6f。

| 绑定 | 准确值 |
| --- | --- |
| owner源码 / 正式目录包 | `f9e3c6cbf7c44676c37ef973389e6176777640ce` / `90b8b3b0970cafa80c076fbf679370144d7b5b9b660668422252d8c4b239800f` |
| 控制 / 单一迁移器 | root `8ab1faa64662e098247d31b90bfb51721d15ee0a`；原唯一005与checksum registry，显式4→5 |
| 新运行代码 | 从原183份Git收件中选**26个**Hunter Python/静态/SQL/依赖锁文件；不带tests/历史证据，不构建Next/Node，不复制其他领域 |
| 本工具SHA256 | `a202d2238fbb69c7c286c6bb0e4256bba03eda8057a166ed761cfda586921bc3` |
| 最终plan | `.runtime/v2-maintenance/hunter-first/f9-90b-v1/execution-plan-v2.json`，`e3f46ed6a8132e3f0760639d1d4cc3c8be6fa1b7d8179e906e7a4a500ef1e61d` |
| 最终29项运维夹具 | `.runtime/v2-maintenance/hunter-first-tests/sealed-1792152926897241000/receipt.json`，`698d0c2f1b0fb6e27d6d0a7b5f0a1fc910ba4994536062311a25fb4e5eadb860` |
| 原owner封存副本3项核对 | 同目录 `owner-copy-checks.json`，`2d14d956bca5557cc3cf93c25b8a2e2e92c869bcd10e299e4030c41ebe749ffd`；未重跑导入/owner套件 |
| 真实只读status | `.runtime/v2-maintenance/hunter-first/f9-90b-v1/readonly-status-v2.json`，`9f40d76ced2778cdd79ea1ac85a81e810e3b72a1f48964ab9081a37fc68048dc`；not_started、Hunter2608、零动作/活库连接/journal写入 |

相对路径以本integration工作树的release-integration为根。v1计划/证据保持原样，因工具前向补正而不再使用；v2的acceptance/worker-plan使用独立版本化文件名，没有覆盖旧计划资产。29项不与早期27/28、准备5项、owner/root462或原Projects32项相加。

## 范围与当前保护

只操作 `ca.ikun.v2.c0lite.hunter`、原 `hunter/hunter.db`、新F9独立release/accepted receipt/plan，以及这个Hunter自有plist。原Hunter env和方向凭据不改。目标库保留同一inode，不导入Auth、不对Projects/Tracking做领域SQL、不恢复旧库覆盖或降schema。网站、Tracking、Alpha、旧PG/监督进程、两个Tunnel、main/ikun.ca/Cloudflare不动。

新保护投影承接实际Projects回执bd437fb7：web54011/start/cwd/executable及54011/54012/54014/54018/54019完整树、socket54014/0600全部复核；不再用87924。固定0ce网站331源码/271构建、原web env/plist、Tracking与其他保护身份/文件、四库inode继续守卫。停止Hunter的保护PID集合包含全部web子进程，不能误把托管IPC/Next纳入停止子树。原旧guard计划不修改，维护投影仅排除获准变动的Hunter自身PID和plist。

Auth/Projects网站writer与Tracking仍运行，因此四库备份各自一致，不宣称全局静止或Auth表内容在本次Hunter维护期间永不变化。本工具不向它们的owner发写请求；只有Hunter停止窗口做逐行保留证明。最后封存版本为2/2/4/4，本次prepare/status未查询活库PRAGMA。

## 实际执行顺序（本轮未执行）

1. 准确clean Git/candidate/main、工具及5个复用helper、F9/90b/原逐行归属与源、Projects实际回执、e9复制库演练、原配置和解释器逐项绑定。复用原Journal单operator锁，只新增Hunter维护phase；不重跑旧端停止或Projects execute。
2. 每窗口新建before_online_N四库在线备份。仍为schema4时核已验演练种子，排除已声明的state/lease时间变化；猎手人工字段、已有业务/账本表变化须重新演练。只复制26个准确文件到新F9 release，拒绝别名、错误hash、额外import文件或不同accepted receipt；保留原release/脚本。
3. 备份原Hunter plist，复核原PID/start/cwd/子树和全部保护后代，只bootout该label一次。原树重父化但同PID/start仍算存活；不强杀。确认Hunter DB/WAL/SHM无RW holder、4011无listener。未知结果先只读对账，不盲目重新bootout/bootstrap。
4. stopped_window_N另备份四库。**schema4必须再核停止后的种子**，堵住before_online→停服期间的合法编辑竞争；有新编辑就保留它，恢复schema4原v2 reader并另做新演练，绝不覆盖。原lease只等自然释放/过期，60秒未过则失败；不删除lease。
5. 停净并保存prearm_intent后，先把Hunter plist原子指向固定F9启动路径，再由原 `python -m hunterradar migrate`执行005。此时未来F9 plan尚未通过schema5正式render，重启也只能失败关闭，不能自动回到旧B4。005确认提交即落盘schema5_observed，之后所有恢复均拒绝schema4/旧reader。
6. schema5前置备份通过后，原 `python -m hunterradar.takeover apply --package <90b包> --package-sha256 90b8b3b0970cafa80c076fbf679370144d7b5b9b660668422252d8c4b239800f --database <原hunter.db> --offline-confirmed`。清空继承环境，固定F9 PYTHONPATH/原Hunter解释器/外采0；没有provider token、HTTP或第二套迁移SQL。
7. after_import_N另备份四库，验证Hunter所有原行/人工字段/revision、非导入表精确不变；state原键逐值hash保持，仅原clock可推进，新键仅允许私有v2命名空间。新增88目录必须停用pending、身份/粉丝/通道NULL、baseline/watch不ready。副作用计数全部0。
8. 原包第二次apply必须duplicate=true/零新增。另核original_result及数据库持久原run确为完整**88/6575/6575**、正确source/ownership/package/kind和零副作用；首轮87或冲突不能被“重放0”洗成PASS。全部表逻辑指纹须不变。标准备份为12份四库+1份schema5前置，共13份；原migrator自己的迁移备份另保留，不混计。
9. 沿原 `night_worker_ops.validate/render`在真实schema5核验后生成新plan，只以 `[<原venvs/hunter/bin/python>, -m, hunterradar, run]`恢复同label、同端口/原env、固定F9兼容reader，强制hard-off。启动前必须有与当前Hunter逻辑指纹完全一致且验证过的schema5备份。新plan的previous_worker_release=None，避免生成退回旧reader的提示。原v2旧plist/release仍保存，但schema5后不得启动。
10. 核Hunter ready200/外采false、所有其他服务/新web完整树和socket/配置/构建及四库inode。成功才追加migrated_domains=hunter，保存真实owner回执、schema5备份与新PID；不能据ready宣称真实采集或永久身份完成。

## 失败恢复与重入

| 状态 | 唯一允许的处理 |
| --- | --- |
| 原树未退出、未知writer或4011仍开 | 保留现场，只读status；不强杀、不盲目bootstrap，不重复原stop_intent动作。 |
| 005尚未提交，原owner inspect确认4且原行/state保护通过 | 只有这一分支能恢复原v2 schema4 reader；如已prearm，核本工具的精确prearm_intent后恢复原plist。不是恢复旧版采集服务。 |
| 005提交后或中断后inspect确认5 | 立刻持久化schema5状态，验证完整当前schema5备份及原行；只装/恢复已审F9 reader。原plist、旧B4和旧613均不可启动。F9文件/plan/备份不完整则Hunter保持停服。 |
| 提交后stdout丢失 | 保留原90b包和批次；恢复F9后，重启维护须新prepare计划绑定新PID/start，root审其hash再以同工具加--resume-recovered。原run/原计数必须再次核对，不能另造包/目录UUID。 |
| bootstrap调用结果未知且job仍卸载 | 不自动重复。若job已loaded，只能核同一精确F9 plist/原intent/原树退净/ready再对账。 |
| 标为complete后再入 | 核最终回执及内部每份原备份/export资产，返回ALREADY_COMPLETE_NO_ACTION；不重复迁移或停启。 |

没有库覆盖、schema降级、通用continuation registry或新常驻服务。prearm不改变此门禁：一旦见到schema5，再见到4也必须报错，不能用降版本号骗恢复。当前代码的--status不读活库，只报告最后记录的schema5状态；未记录不代表已证明活库仍4。

## 准确命令与证据

Git提交后将本次准确40位candidate及实际argv另写同一私有输出目录 `reviewed-execution-command.json`，由最终回复给出其hash，避免Git自引用。root必须先审此candidate/plan/argv再执行，不改成任意HEAD，不使用旧v1计划。

可直接只读查询：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/lvlei/.local/bin/python3.11 release-integration/scripts/hunter_directory_maintenance.py --status --plan /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/v2-maintenance/hunter-first/f9-90b-v1/execution-plan-v2.json --plan-sha256 e3f46ed6a8132e3f0760639d1d4cc3c8be6fa1b7d8179e906e7a4a500ef1e61d
```

本地29项均为模拟launchd/进程+新临时SQLite；原owner封存copy额外3项只读检查验证本工具与真实F9回执/原run/88 pending行兼容。e9演练及5项原wrapper夹具保持不变，没有重算成新总数。当前Hunter2608、网站54011和Tracking25225保持；运行release/accepted/plan/plist未安装改动，维护phase尚不存在。所有真实平台/新WSS/Watch/Next构建为0。Tracking后续独立维护，不收其新测试号工作树，不夹带Alpha observer或真实样本。

机器摘要：[hunter-only-maintenance.json](./hunter-only-maintenance.json)。
