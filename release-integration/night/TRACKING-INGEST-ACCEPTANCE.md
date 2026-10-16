# Tracking 网站受理集成验收

状态 **PASS_WEBSITE_RECEIVER_PROTECTED_V2_PUBLIC**。冻结业务来源 `6067658d6092e4d046a8691e8f2f93b34c717801`，协议父 `c8fb68901db9d4b00300ef483c8d20f9de33f7c6`，总管批准 `2c55f927bcbcc0d2b47472d84156ffa38826876b`。集成运行源码提交 `0b0f4549758b74ec5defc06493054f41d80d439d`；网站正式 build `X0CYNNjMlhJWNcjEpx1PF`，331 个源码、271 个构建哈希已绑定。实际 v2 已从已验语音 `19863b2af031fc2592bb6d73b7161efc77b0bd1d` 升级为 `0ce180c33ea4be350ac57daa7dbfa5b5221e58cb`。总管最终控制 `99109bf878837b4522ae114454c53c0aa89f6bce` 已核对准确候选；原审批入口执行通过。

公网收尾完成于 **2026-10-16 15:36:15（上海时间）**：

| 实际站点检查 | 结果 |
| --- | --- |
| 无副作用受理探针 | 无凭据401、错方向401、错scope403、有效方向空对象422、未知receipt404；合法观察POST为0；证明接收端不再501 |
| 原数据保留 | 全部Projects表内容指纹在探针及整批公网验证后均不变；原主页1条、Hunter信号1条、Tracking零订阅/零推文 |
| 公网真实会话 | 原admin五项GET200；临时普通用户五项GET200、Projects/Tracking六种写方法403，首页无新增入口，语音默认关闭 |
| 方向隔离 | admin人类Cookie单独POST内部受理端401；新方向值仅在网站0600私密配置，未进入argv或六份日志，未写Worker |
| 撤销及收尾 | `c0_ingest_viewer_1792135640`经原CLI禁用，口令字段移除；既有SSE正常EOF，仅2个heartbeat/零业务事件，四API401；原admin仍200；全部旧临时账号也禁用 |
| HTTPS门禁 | 无Cookie四个HTTPS路径均TLS验证成功、由Cloudflare403；这个拒绝结果与已授权200分开记录，本轮没有新Guest窗口验证 |
| 进程保持 | 网站PID67800→87924；Hunter2608、Tracking25225、Tunnel39523前后保持；7份Worker env/config/plan/plist SHA256一致，三个业务作业独立、三ready200 |
| 四库与备份 | 原四库inode/路径/schema保持，均0600、单链接、integrity/FK通过；升级前/后/禁用账号后各4份在线备份，共12份hash复核 |
| 运行参数 | 正式next start、loopback4000、Node堆上限768MiB、遥测关闭；launchd RunAtLoad/KeepAlive、ThrottleInterval30保持。所属进程RSS快照164.2MiB，不是峰值或长时压测 |

公网不可变18份附件及总回执位于 `release-integration/.runtime/tracking-ingest/public-evidence-1792136175415559000`，总回执SHA256 `d41b93500af1d4cd69fcaac8abdc51b39ba0e27054ab14ba39e2825da46bd1fd`。331源码/271compiled部署字节复核通过；本地38份不可变证据保留原样。准确逐文件hash、PID、四库身份、三批备份及新字段元数据见机器报告。旧版服务、主域名、既有Cloudflare均没有本轮变更。

仅接收原 owner 的 13 个冻结路径，55 项源输入逐一匹配；网站 helper 仅保留原双 readPaths 精确变换，没有覆盖 gateway/layout/root。新增 `tracking_observations.py` 已进入源码清单、Git archive 部署复制和真实启动导入；原 Auth、只读权限、B3/B4/C03、语音及主页守卫保留，77 原来源核验未删，原哈希实际保持70。未迁移 schema，未修改两 Worker 源码或构建它们。

| 验证 | 通过结果 |
| --- | --- |
| 冻结 Projects 原回归 | 246 项；内含 Node 16/14/11 子集，不另加总；一次依赖弃用提示，无失败 |
| 实际生产 Next/UDS/页面 | 最终 108 项；两个角色、1440/390、真实 B1 和独立四库 |
| 原 B3 组合回归 | 76 项；原 Hunter→Projects→commands→Tracking、C03、四库隔离、撤销；合成来源 |
| 原无声语音浏览器 | 48 项；默认关闭、真实metadata、替身 Speech/时间/帧、取消和撤销 |
| 独立 Auth bundle | 3 项；构造器、singleton、角色和撤销错误路径 |
| 启动与失败恢复 | 最终14项；8项私密加载拒绝，成功启动参数不含新值，bootstrap/ready失败恢复原文件及不操作其他job |
| 正式构建 | Next build、网站 typecheck；共用 heavy lock 串行；两个 Worker compiled SHA 未变 |

这些套件有功能交叉，不公布相加的唯一测试总数。108 项最终套件已验证两种实际事件、六字段持久回执、同ID/hash幂等、异hash409、最大emoji/控制字符、int64最大值及九位时间字符串不变、Tracking精确128KiB和Hunter64KiB、非法UTF8/surrogate/小数拒绝、真实HTTP丢ACK后单POST+原hash GET、存储故障503与事务回滚、scrub422/未知404、真实Next重启回查、人工字段/评级/membership/revision保留、普通用户服务器403和整页写入口隐藏、禁用401。其他两个夹具库哈希未变，Projects DB/WAL未存推文正文、未生成命令；IPC128KiB原代码及原回归保留。

前两次真实Next套件失败均属夹具：第一次到34项，“其他项目”仍active，未出现“加入主页”；第二次到28项，补移除操作缺JSON头，被B1正确拒绝。修正隔离API准备并填足19条分页数据后最终108项通过，没有改业务代码。原失败回执和12项早期ops子集保留，不算新通过数量。原B3复用脚本有一条未作为断言的历史“501”说明；本次受理能力由独立108套件证明，未改写该原始脚本或旧报告。

全部新证据在私有不可变 `release-integration/.runtime/tracking-ingest/evidence-1792135382141172000/`，38份hash见 [tracking-ingest-acceptance.json](./tracking-ingest-acceptance.json)。新测试脚本及原B3/voice脚本快照、两次失败回执、JUnit、构建日志、截图各自保留。视觉抽查管理员桌面、普通用户390、语音390正常；原语音公网证据没有覆盖。

总管已审 `0b0f454` 的七份操作脚本，并以最终控制99109批准0ce完整候选及测试/收尾助手。外层不变量失败会记录实际网站SHA/PID/rollback，不假定已自动回滚。激活前网站缺 `PROJECTS_INGEST_TRACKING_TOKEN`；此次在保存原web env/plist/owner之后生成新独立随机值，原web.env 0600仅新增这一字段；launchd argv只含私密文件路径，启动器校验准确自有路径、普通文件、uid、0600、nlink、大小后读取该字段。错误路径/权限/符号链接/硬链接/直传重复token/非法JSON/短token/过大文件均失败关闭。失败恢复原三文件，因此撤销新字段；隔离测试用launchctl替身，未执行生产回滚。

激活包装器已先备份四库、仅重启新v2网站和既有Projects IPC，并完成上述四库、Worker、数据保留及公网检查。新字段未写Tracking作业；合成合法POST/丢ACK/重放仅在隔离库。未执行真实来源调用或实际扬声。

已执行命令：`/Users/lvlei/.local/bin/python3.11 release-integration/scripts/upgrade_tracking_ingest_site.py --candidate 0ce180c33ea4be350ac57daa7dbfa5b5221e58cb`。没有自动审批拒绝或改入口重试。

回滚副本：`/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/rollbacks/19863b2af031fc2592bb6d73b7161efc77b0bd1d-20261016-152706`。必要时先另作四库在线备份，仅恢复原web plist/env/owner与19863 release（build `toKW74u9T1cCk_lyTUZXo`），bootstrap同一web label，核对三ready和两Worker原PID/配置；旧env快照没有本轮新字段。四库保留原位、不回写备份、不停止Worker/Tunnel；保留本轮回滚证据和当前release。**本轮未执行生产回滚或故障注入**，失败恢复的14项证据来自隔离替身。

**能力结论仅为网站受理并可按原hash reconcile。** c4de没有delivery/claim/ACK/reconcile写回任务，未改tracking.db pending；expired404仍unknown，不重建正文或伪造ACK。不合main、不push、不动旧版/主域名/既有Cloudflare/共享Watch，不执行真实采集或实际扬声。完整投递及TTL闭环仍阻断。

来源：[tracking-ingest-receiving.json](./tracking-ingest-receiving.json)；操作范围：[tracking-ingest-operations.json](./tracking-ingest-operations.json)；准备清单：[TRACKING-INGEST-INTAKE-CHECKLIST.md](./TRACKING-INGEST-INTAKE-CHECKLIST.md)。
