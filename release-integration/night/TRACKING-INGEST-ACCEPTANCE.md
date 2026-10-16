# Tracking 网站受理集成验收

状态 **PASS_LOCAL_PENDING_FINAL_ROOT_REVIEW_AND_ACTIVATION**。冻结业务来源 `6067658d6092e4d046a8691e8f2f93b34c717801`，协议父 `c8fb68901db9d4b00300ef483c8d20f9de33f7c6`，总管批准 `2c55f927bcbcc0d2b47472d84156ffa38826876b`。集成运行源码提交 `0b0f4549758b74ec5defc06493054f41d80d439d`；网站正式 build `X0CYNNjMlhJWNcjEpx1PF`，331 个源码、271 个构建哈希已绑定。实际 v2 仍为已验语音 `19863b2af031fc2592bb6d73b7161efc77b0bd1d`，未激活本候选。

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

总管已审 `0b0f454` 的七份操作脚本。最终再审增量：外层不变量失败会记录实际网站SHA/PID/rollback，不假定已自动回滚；增加了测试与收尾助手，尚未执行。当前网站缺 `PROJECTS_INGEST_TRACKING_TOKEN`。获准激活时，只在保存原web env/plist/owner之后生成新独立随机值，原web.env 0600仅新增这一字段；launchd argv只含私密文件路径，启动器校验准确自有路径、普通文件、uid、0600、nlink、大小后读取该字段。错误路径/权限/符号链接/硬链接/直传重复token/非法JSON/短token/过大文件均失败关闭。失败恢复原三文件，因此撤销新字段；隔离测试用launchctl替身，未执行生产回滚。

激活包装器会先备份四库，前后核对四库inode和原Hunter75b/Tracking640的7份env/config/plan/plist、两Worker及Tunnel PID；仅重启新v2网站和既有Projects IPC。新字段不写Tracking作业，不接真实来源。部署后只允许无写入探针401/403/422/未知receipt404，并比对Projects全部表内容指纹不变；合成合法POST/丢ACK/重放只在隔离库。现有业务读权限、原数据、临时账号禁用、日志、备份和回滚凭据随后核对。

待最终准确候选获准后执行：`python3.11 release-integration/scripts/upgrade_tracking_ingest_site.py --candidate <最终完整SHA>`。脚本强制candidate等于干净HEAD，不可替换成旧source SHA。若自动审批拒绝，不换入口/窗口执行；保留准确候选、命令和原拒绝原因给用户。

**能力结论仅为网站受理并可按原hash reconcile。** c4de没有delivery/claim/ACK/reconcile写回任务，未改tracking.db pending；expired404仍unknown，不重建正文或伪造ACK。不合main、不push、不动旧版/主域名/既有Cloudflare/共享Watch，不执行真实采集或实际扬声。完整投递及TTL闭环仍阻断。

来源：[tracking-ingest-receiving.json](./tracking-ingest-receiving.json)；操作范围：[tracking-ingest-operations.json](./tracking-ingest-operations.json)；准备清单：[TRACKING-INGEST-INTAKE-CHECKLIST.md](./TRACKING-INGEST-INTAKE-CHECKLIST.md)。
