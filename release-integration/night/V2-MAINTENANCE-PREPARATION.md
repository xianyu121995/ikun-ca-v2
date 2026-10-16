# v2 单 writer 维护准备

状态 **PREPARATION_ONLY_PENDING_BOUND_INPUTS_AND_EXECUTION_REVIEW**。沿45ad方案前向补齐；旧侧停采已由总管c6259b验收，本阶段不再调用旧端 execute。没有停止v2、打开运行库连接、导入、升级、接收代码到领域路径、构建或发布。

最终只读预检：`release-integration/.runtime/v2-maintenance/preflight-1792145989342.json`，SHA256 `c514d0aa3eefdc5f6281d7ac674c91a82025363f9df76b94148bd1258046c229`。

| 当前唯一 writer | label / PID / 受托管树 |
| --- | --- |
| Auth + Projects | ca.ikun.v2.c0lite.web / 87924；87924→87976→87978（Projects IPC），87924→87986→87987（Next） |
| Hunter | ca.ikun.v2.c0lite.hunter / 2608 |
| Tracking | ca.ikun.v2.c0lite.tracking / 25225→25229→25230 |

Projects socket为 `/private/tmp/ikp-R8jWuG/p.sock`，0600，现有holder87978属于web树；没有读取IPC token。四库仍在原DATA_ROOT，inode依次Auth20187691、Projects20187927、Hunter20535150、Tracking20685563，0600/单链接/物理独立。只查文件身份，没有连接活库；最后封存版本为2/2/4/4，不能把旧备份元数据说成本次重新查询活库的PRAGMA。旧14份SQLite备份metadata/integrity/FK及66个资产引用哈希已复验，当前没有生成新活库备份。

v2仍0ce180c / BUILD X0CYNNjMlhJWNcjEpx1PF，331源码/271构建哈希匹配，三ready200、双外采false。预检复用封存 `takeover_operator.guard` 核验Alpha、旧PG/监督进程/共享Tunnel及受保护文件，当前8保护身份保持。这个guard仅用于**维护前**；维护执行器必须把获准停启的v2三job与永久保护的旧端/原Tunnel分开，不能停v2后仍要求旧v2 PID不变。

## 准确收件边界

| owner准确版本 | 本次核对 | 使用范围 |
| --- | --- | --- |
| Projects09afbcfd7ba7d809750d4b27c7599c952335b35f | 59源码/6证据 | 原prepare/import；研究完成事实只存专属metadata；schema2、worker导出DTO不变 |
| Hunter bf94dd0f93a75c2d8c7e8ebc58a642bf698016ac | 20源码/保留输入 | 原prepare、唯一migrator显式4→5、原apply/同版本备份恢复 |
| Hunter sample613262279996700fd9418b8037cf1eb6ff38551e | 19源码/保留输入 | 仅收件，不运行样本；覆盖retention的sample fence采用此已审前向版本 |
| Tracking70c138d3fcc440a94b19b0ba79f0b3795f6e202e | 67源码/6日志 | 原唯一转换器和import CLI，schema4不变；不收未审sample工作树 |

Tracking准确收件说明来自已审文档提交9c3a2c2cfe88bdc0025c73afd058f4c5efb94fe4；70c内旧EVIDENCE仍有6处历史hash，不拿它替代当前证明。所有源码只读准确Git对象，9c3a的67个输入与70c逐一一致。Projects3份XML不入Git，严格核原owner留存路径/hash，源码不回退读owner工作树。两次早期preflight读取边界失败回执保留；不是服务/数据故障。

最终源manifest `8f5a453a705dbe0ba4c3957c94098ba05684a95b1ef54ca16243fa90aa8fac1f` 位于总管 `var/takeover-execution/final-inputs/source-manifest-v1.json`；PG归档hash为 `d0e25f6472aca37ff408ff4ff8219fb6953ab698e053add40dc14e7f44431d46`。两者不能混同。原Watch快照明确不是当前provider状态证明；本次不读取远程Watch。

## 工具与维护顺序草案

当前可运行的**只读**预检命令如下，输出必须是尚不存在的新0600文件、父目录0700；没有执行分支：

```sh
/Users/lvlei/.local/bin/python3.11 release-integration/scripts/preflight_v2_takeover.py --output /ABS/PRIVATE/NEW/preflight.json
```

Hunter新桥接 `takeover_hunter_map_bridge.py` 仅纯文件：要求真实Projects apply receipt及独立最小export/hash、获审package/importer源码hash、最终manifest/hash。只取public.projects的已持久化verified非空X ID，原样复制project_id与source_sha256，不生成ID、不猜handle，不把研究事实送worker。空身份保留未解析计数；重复旧引用/X身份和未知字段失败关闭。输出单一Hunter DTO和绑定所有输入/输出/转换源码hash的sidecar，0700/0600、不覆盖；同输入重入核原文件，partial保留。**18项合成检查通过**，未对真实映射运行。证据及准确源码hash见机器摘要。

Tracking继续唯一原owner `python/integration/convert-takeover-map.py`；CLI参数为 `--projects-export`、`--projects-export-sha256`、`--pg-dump-sha256`、`--snapshot-manifest-sha256`、`--output`，输出实际字段为 `source_manifest_sha256`，并独立绑定export/master/dump/package四hash。不另开发Tracking DTO转换。

后续准确命令必须在以下绑定齐全后生成给总管审查，现在不运行：

1. root批准逐ID Projects decisions、各域ownership/独立X身份证据/原时间/基线、Alpha及未知排除、输入路径及SHA；数量和research_status本身不构成所有权或成员批准。
2. 从已审代码生成不可变CLI/reader包，并用新隔离副本演练。这里只核Git输入，没有复制领域代码或发布运行release；不调用会覆写现有网站接线的preview/sync脚本，不代写业务引擎。需要Next/Chrome验证时持唯一heavy lock。
3. 重新preflight、向新目录四库在线备份；精确停止Hunter、Tracking及web整棵IPC/Next树，核原PID/start全退、端口/socket关闭和没有未知writer，再做静止四库备份。Auth不导入、不bootstrap、不改用户/会话；停写窗口前后核内容及物理inode不变。
4. Projects只用09af原prepare/import：prepare的`--dump/--expected-dump-sha256/--decisions/--expected-decisions-sha256/--output`；import默认干跑，apply另需`--apply --writer-stopped`，绑定package/receipt/mapping路径和hash。提交后导出失败先原包对账重导，不重新造canonical。
5. 真实Projects持久export及apply receipt出来后，才运行Hunter文件桥；Tracking直接原转换CLI。Hunter prepare使用原`--source/--source-sha256/--ownership/--ownership-sha256/--projects-map/--projects-sha256/--output`。
6. Hunter新兼容reader包须就绪且来源硬关闭，全部writer已退，再由原`hunterradar migrate`显式4→5；原takeover apply需`--package/--package-sha256/--database/--offline-confirmed`。每次提交后另留通过验证的schema5完整备份；旧B4不能读5，提交后不得回到旧binary或降低版本号。
7. Tracking原import CLI使用`--config/--bundle/--bundle-sha256/--projects-map/--projects-map-sha256/--ownership/--ownership-sha256`，实际提交另加`--apply`。没有虚构`--writer-stopped`旗标；外层维护窗口负责所有writer退出。独立离线配置要求adopt-only、remote/dedicated关闭、无token_file/外采token；不修改原运行配置来凑CLI通过。
8. 三域计数闭合、同包二次零新增/零提醒、人工字段/rating/membership/revision保护、四库identity/integrity/FK和Auth内容保护通过后，做第三批四库及schema5备份。按已审兼容矩阵恢复web/IPC→Hunter新reader→Tracking，外采仍关闭。实际公网权限/真实来源样本另验，不用ready或历史导入冒充。

跨域已有提交后不声称全局回滚；禁止替换运行库inode、ATTACH/跨库SQL或回写旧备份。按原包幂等续跑或owner已审补偿；不兼容/未知结果保持对应领域暂停。此草案没有任何stop/apply/publish执行入口，完整可执行维护argv和最终输入hash仍须另交总管批准。

后续Alpha连续投影先查可复用工具；同观测生成器可输出两份DTO：Hunter维持613原8键，Tracking按待审24fc字段准备夹具。两份摘要各按其协议计算并绑定同sidecar，不强行共用hash，不把未审Tracking样本代码收入本次包。该后续项不阻塞本页工具收件。

机器摘要：[v2-maintenance-preparation.json](./v2-maintenance-preparation.json)。原45ad清单保留为历史，不把其中旧端“尚未停止”表述当当前状态。
