# 接管维护导入准备清单

状态 **PREPARATION_ONLY_WAITING_ROOT_EXECUTION_BATCH**。唯一执行号 `IKUN-ONLY-2026-10-16` 已由root认领；本窗口不另认领、不停旧版、不请求平台。依据root `0157f9f3315d13b3959a538574a8471bbf4dd581`。本清单尚未授权停v2、导入或部署；原501批次继续冻结。

只读核对时间 **2026-10-16 15:52:50（上海时间）**：实际网站 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb` / build `X0CYNNjMlhJWNcjEpx1PF`，331源码/271compiled匹配；integration报告基线 `fa51e92c66a374b95c5397cd50cdd021ebe1496b`，main `63e8a2857241c6a76226f21435e40db9736a1e7e`。三ready200、Hunter/Tracking外采false。启动时间、cwd、进程树及四库元数据仅记在本轮快照，执行前必须重新核验，不能照抄旧PID操作。

| 领域唯一writer | 对应精确launchd job | 此刻PID | launchd cwd |
| --- | --- | --- | --- |
| Auth + Projects（含托管私有IPC） | `gui/501/ca.ikun.v2.c0lite.web` | `87924` | `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/releases/0ce180c33ea4be350ac57daa7dbfa5b5221e58cb` |
| Hunter | `gui/501/ca.ikun.v2.c0lite.hunter` | `2608` | `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/jobs/hunter` |
| Tracking | `gui/501/ca.ikun.v2.c0lite.tracking` | `25225` | `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/jobs/tracking` |

网站须整体停止：当前web树为87924→87976→87978（托管IPC/Python）及87924→87986→87987（Next）；不能只kill IPC/Next让父级恢复。Hunter此刻Python PID2608；Tracking树25225→25229→25230。只可对核验归属的job执行bootout，不能用宽泛pkill；停后核验原父子PID+启动时间均退出、监听/IPC socket关闭、没有其他进程持有目标库写句柄，再让本域导入CLI成为唯一writer。存在残留或未知writer即停止导入。

数据根 `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/data`，原 `auth/auth.db`、`projects/projects.db`、`hunter/hunter.db`、`tracking/tracking.db` 全部保留。当前inode：auth `20187691`、projects `20187927`、hunter `20535150`、tracking `20685563`；均0600、单链接、独立身份、integrity/FK正常。Auth不迁、不bootstrap、不改用户/密码/权限。既有12份在线备份只读复核通过，**本次没有创建新备份或复制运行DB/WAL**。Tunnel `ca.ikun.v2.c0lite.tunnel` / PID39523不属于维护停服清单。

## 执行批次到齐后的固定顺序（现在不执行）

1. **准入/演练**：取得root已审三域工具完整SHA、最终一致输入与归属清单、每份SHA256、schema/checksum兼容说明、dry-run差异/冲突/排除计数和运行参数。先在新隔离目录从SQLite online backup副本做完整演练，验证同包二次零新增/零通知、不改人工revision。重型构建确有必要才持共用锁；不能重建或部署501报告HEAD。
2. **维护前证据**：重新核对上述job的label/PID/启动时间/cwd/plist/env/source hash、实际DATA_ROOT和四库inode/schema。调用既有SQLite backup API模式，向本次执行号下**新建0700目录**逐库备份，文件/receipt0600，核对SHA256+integrity/FK。可复用已审 `release-integration/scripts/deploy_b3_tracking.py:backups()`；不能cp在线DB/WAL。在线单库一致不冒充四库分布式原子快照。
3. **建立唯一writer窗口**：本次若导三域，先bootout上述Hunter和Tracking job，再bootout web及其托管IPC；确认全部相关writer退出后再做第二批四库静止备份。Auth也因web停而静止，但不参与导入。旧端最终快照/停采由root负责，本窗口不得重复停旧或擅自停止文件所述手工Hunter。
4. **Projects先行**：仅运行已审本域工具，在原 `projects.db` 内受控事务导入。保留现存v2手工字段、评级、成员关系及revision；冲突隔离，不靠名称/handle猜合并，不默认A/B。固定旧ID→`prj_UUIDv4`映射及最小canonical导出，绑定最终输入hash和执行号。其余导入器只读取这个版本化映射文件，不跨库查表；评级唯一写在Projects。
5. **Hunter / Tracking各域**：沿已审输入/map分别调用原owner工具，库路径仍为原 `hunter.db` / `tracking.db`，不得ATTACH、跨库SQL、旧库替换新库、os.replace数据库或导旧Auth。每域单事务/持久receipt、失败本域回滚，导入器关闭后才允许相应原job恢复；工具须明确保留inode。Hunter名单/基线/7天发现和稳定target账本、Tracking已有自有Watch adopt-only/15天推文/小tweet_id账本均按owner批准规则处理；只认肯定自有稳定ID及原flags/原组，不凭组名猜归属，不整形远端flags。历史为非live/replay，通知和实际扬声为0。Alpha/不明全部排除，Watch add/delete/update为0。
6. **提交检查/恢复**：停写期间核对四库身份/schema/checksum、integrity/FK、计数闭合、冲突隔离、受保护人工数据指纹；Auth导入前后内容不变。完成第三批新目录备份。按兼容矩阵恢复web→托管IPC并验证Auth/Projects，再恢复Hunter和Tracking，初始保持外采关闭；三ready和网页读权限不代表真实采集成功。若需新运行版本/配置/schema，root批次必须单列精确SHA和回滚兼容范围，不能由本清单默许部署。
7. **故障/幂等/回退**：按执行号+输入hash记录每一步和每域receipt，重入先查进度，不重复停服/导入。单域事务失败回滚；跨域已有部分提交时不声称全局回滚，不覆盖四库备份或换inode。保持相关业务暂停，先凭同包幂等续跑或已审owner补偿；缺补偿方案则交root处理，不能直接恢复真实采集。备份恢复演练只在另一个新目录；不能用代码回退冒充数据回退。旧release、plists、配置、checkpoint、备份全部保留，Alpha/旧PG/Tunnel/域名始终不动。

## 尚缺依赖 / 放行条件

- root交付最终冻结输入、肯定ikun归属及Alpha/不明排除清单；旧手工Hunter最终水位、停采授权和无双采集证明由root确认，未满足不得开启v2采集。没有在本窗口核验或操作旧端。
- 原Projects/Hunter迁移工具、Tracking adopt-only的完整冻结SHA/输入契约/独立回归、事务及幂等/补偿说明；目前本窗口未收这些后续候选。
- 三域数量对账和唯一canonical映射、现有人工记录冲突处理、过期/历史不通知证明；同账号多WSS与Alpha连续保护由root先过门禁，不新开探测连接。
- root明确维护批次、确切工具命令/自有配置增量/恢复顺序；真实样本2猎手+1追踪及费用/限频门禁另行执行，本清单不执行。Tracking delivery/ACK/pending与完整TTL闭环仍按后续owner审查，不由导入或ready通过代替。

证据：`release-integration/.runtime/takeover-preparation/snapshot-1792137170094933000.json`，SHA256 `1fe2978b444cbf2b353d9e688ddc57b5921517f08604b0fd2e3f0f23ae410385`。本批次操作计数：停v2=0、导入=0、新库备份=0、平台请求=0、Watch写=0；只读核验和本清单以外没有业务改动。
