# Hunter F9 维护前准备

状态 **PREPARED_READER_GUARDS_AND_CLONE_REHEARSAL_ONLY**。运行库、Hunter进程和运行配置未动；此工具没有execute入口。Projects首批已实际通过（报告ea401a9、root fc537a6），下一阶段只准备Hunter独立维护，不能把Projects完成写成Hunter/Tracking也已迁入。

| 输入或证据 | 精确绑定 |
| --- | --- |
| Hunter owner | `f9e3c6cbf7c44676c37ef973389e6176777640ce`，root8ab1faa；15 Git输入及11原证据匹配，183 Git文件暂存私有工作区 |
| 正式目录包 | `90b8b3b0970cafa80c076fbf679370144d7b5b9b660668422252d8c4b239800f`，显式`not-applicable:directory-v2`，不需要空/伪Projects map |
| ownership / inputs manifest | `a79cfdf0ed2592bb1e686ef2233ea7c5abeaeefcf151075923020c2c9c48769f` / `5e9d62253ab0b059284d220485fa52c8a27a0a0bfc7a03a5a3d6b42badf204b9` |
| 新复制库演练回执 | `.runtime/v2-maintenance/hunter-directory-rehearsal/clone-1792150656666089000/REHEARSAL_ONLY.json`，`e9af5e71f832003cfe51c9d730a701a773a13686b168dd22a8a327db9c3ee18a` |
| 准备回执 | `.runtime/v2-maintenance/hunter-f9-preparation-v1/PREPARATION-ONLY.json`，`1d33301b42c993d6091914d08e7a436daae7a97ff8a407f8c0c96b6fa1226b37` |

相对路径根为本integration工作树的release-integration。敏感原行、Hunter身份及目录UUID不写入本报告或Git。

## 实际完成的离线验证

仅从封存after_v2_hunter schema4备份 `e74a27abc61da15d7b47e8bb1fedef412221dae6fb108d12d02b5a5648278192` 克隆至新私有hunter.db。固定F9源码、生产Hunter原解释器，以清空继承环境、固定PYTHONPATH、外采0，运行原 `python -m hunterradar migrate`，原唯一005显式升级schema5；随后原 `python -m hunterradar.takeover apply ... --offline-confirmed` 使用90b8正式包，并同包重放。没有运行run/api/worker或连接任何平台。

原2条猎手记录全部字段保留，所有原行保留（仅原retention_clock_highwater按原协议推进）；原非导入表精确不变。新增88条停用pending目录，运行ID/粉丝/通道NULL、baseline_ready/watch_covered均0；6575私有事实。重放业务/私有事实/私有回执新增均0，全部25表逻辑指纹不变、同一克隆inode；另生成并验证schema5完整备份。来源封存副本和输入包hash不变，克隆UUID绝不给正式运行使用。初次暂存因调用方漏umask077触发权限守卫，失败目录保留；未进入DB克隆或迁移。纠正调用方后新目录全0700/0600，没有修改owner业务。

原 `night_worker_ops.validate/render` 在新schema5复制库和独立假root验证 **5项**：固定Python入口通过、原render通过且未安装job、外采1拒绝、schema4 receipt启动schema5拒绝、错误reader哈希拒绝。最后恢复原夹具文件并再验证。此5项不与owner462项、root462项或原运维32项相加，不是实际Hunter启动/恢复证明。

## 当前保护投影

旧 `takeover-operator-plan.json` 原件/hash保留。新投影从它复制，只把已正式验收的v2_web更新为Projects实际receipt中的54011/start/cwd/executable；另逐项复核54011/54012/54014/54018/54019完整树，以及 `/private/tmp/ikp-aUeczB/p.sock` 的持有者54014/0600。不能继续用87924，也不能只验主PID而遗漏托管Projects/Next。

只读prepare仍核Hunter2608、Tracking25225及全部原保护进程/文件/四库inode，三ready200、双外采false。另生成**仅供Hunter维护期间**的投影，移除获准操作的v2_Hunter进程和Hunter plist旧hash约束，其余包括新web完整树、Tracking、Alpha、PG、Tunnels、原env/plan均保留。此投影文件不是自动停服许可，真实维护脚本必须在每个动作前后调用并验证。

## 冻结reader与下一准确执行包

工作区生成 `future-worker-plan.json` / `future-acceptance.json`，拟定独立runtime release为 `~/Library/Application Support/ikun-ca-v2-c0-lite/releases/f9e3c6cbf7c44676c37ef973389e6176777640ce`。只用F9的183个原Git文件、原依赖锁和现有Hunter解释器；沿原night_worker_ops已有Python入口 `[<原venvs/hunter/bin/python>, -m, hunterradar, run]`，同一Hunter env文件、不改变方向凭据/外采flags。不需要Next、Node重新构建或新服务，不执行旧deploy_b4_hunter新装流程。

实际运行目录/receipt/plan/plist尚未写入；没有对当前schema4活库调用schema5的生产validate。生产校验会在唯一005实际迁移后才通过，不能借更改receipt版本绕过。schema5自身不能挡住旧613的v2未知命名空间；必须固定本次F9 reader/CLI，迁入后禁止回退旧613/旧apply。旧B4 reader拒绝5，不能自动退回它。

下一准确执行器及argv仍需root审定：新四库在线备份→仅Hunter job短停/核原树退净与未知writer/4011→原lease释放或自然过期（不删lease）→原migrator005→原90b8 apply→新schema5备份/原行与pending/私有命名空间保护/同包重放0→原wrapper切到固定F9 hard-off reader→所有其他服务/新web树/四库inode与ready复核。schema5提交后未知失败只能使用已审F9兼容reader或保持暂停，不能覆盖库/降schema/启动旧reader；必须在停前备妥这个恢复分支。

工具只读命令：

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/lvlei/.local/bin/python3.11 release-integration/scripts/prepare_hunter_directory_maintenance.py --output /ABS/NEW/PRIVATE/OUTPUT
```

当前private输出的未来运行路径是计划，不表示已发布。实际原库写入/服务动作/新WSS/平台/Watch均0。88目录不是已核验身份或已接管采集，71基线仍not-ready；不把测试号混入旧包。Tracking后续只收总管新准入的原owner版本及正式Projects导出，当前也未迁入。

机器摘要：[hunter-directory-maintenance-preparation.json](./hunter-directory-maintenance-preparation.json)。
