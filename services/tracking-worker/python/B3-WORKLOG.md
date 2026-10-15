# B3 开发记录（尚未交付验收）

基线 9e2835cafc95cb15dc4b8178abacf0c604018536；放行 9e1d1aa53d58b9ee4f23f5ec1356da0ebbf1e362；产品增补 c3f535b0342253a74905b65ea87bd9b819624061。只在 services/tracking-worker 与 schemas/tracking 修改，未合并/推送/部署。B0/B1/B2/UI 按 integration/prepare-b3.py 的完整 SHA 导出到忽略的 .b3/preview，未改其他 Worktree。

## 当前代码

原 Worker 的所有权、回查、quota/429、WSS ACK/pong、重连、generation、REST100窗口仍沿用。加入600名额只报错不淘汰；commands/inbox/hash/真实远端回执、sub_ID映射、SSE事件与pending观察outbox。服务端不接受人类Cookie，不调用session getter，不另存人类会话；BFF/页面/Action使用固定B1实际guard，浏览器项目引用通过固定B2 IPC核验。

SQL唯一权威 schemas/tracking，显式 init/migrate，普通serve/HTTP/ready不DDL。保留旧四列ledger、旧tweets/receipts；活跃旧身份必须停下另审，不能清库。独立_migration_checksums、future/hash/path/失败回滚测试。Runtime使用B0 guardian，子进程环境裁剪。

## 已执行记录（不可作为最终SHA验收）

- 旧核心26项先跑通过；全部适用保障后续合入新测试。
- Python全量第二次62通过（含1个pytest wrapper，内部Node当时6项；不再相加）。日志 artifacts/b3/python-pass2.log。
- Node第一次4/5，发现fetch Response头不可变造成已受理却返回500；修复后5/5，再加入公共命令回查后6/6。失败和成功日志均保留。
- 新迁移测试首轮四列空旧checksum错误拒绝，修复后通过；新增保留期测试首轮缺time导入，已修复复跑。
- 第一轮完整Next/Auth/UI/Tracking构建通过；receipt/source hash已过期（随后有代码修改），不能当最终构建。build-1.log保留。共用重任务锁receipt为 main/var/coordination/tracking-worker-a11a80a1-a2ab-4200-a5cc-16e3c32bfbfb.json。
- 新Node24源码入口生命周期：显式初始化、SIGTERM退出0、父SIGKILL后私有树回收、重启通过；artifacts/b3/lifecycle-source-first.log。正式compiled launcher还需最终构建后复验。
- Chrome新B3批次尚未启动；integration/tests/browser.test.mjs已写，不能引用旧版browser成绩。

## 历史暂停阶段的资源与剩余任务

用户最新转达上级总管Claude：仍暂停完整构建和Chrome；集成窗口正在生产构建/部署。只整理代码和证据、跑轻量测试，待项目总管或Claude明确解除，不能因锁空闲自行恢复。当前没有本窗口驻留测试进程（只读PID检查为空）。

轻量硬化、回归、报告与旧41覆盖映射已完成。候选前向提交后等待明确通知；获重任务恢复后，以同一主仓库with-heavy-lock.py完成最终串行构建、compiled launcher及真实浏览器1440/390，修复新发现后复验，再补最终构建/浏览器/hash/锁receipt交总管审阅。

## 本轮轻量收尾

- 最终pytest **89通过**，内部6个Node实际入口测试仍只作1个wrapper计数；分组25/10/1/26/1/1/23/2，详见B3-EVIDENCE.json。新增保留原别名/硬链接/owner、配置权限保护，补过期stop竞态及外部flags删除保护。
- 当前Node24源码入口SIGTERM=0、父SIGKILL后私有进程树回收和重启再次通过；不能代替compiled入口。
- 方向凭据格式校验不泄露内容；结构/索引/ledger损坏拒绝启动；已有项目X稳定ID可补缺值但冲突不覆盖人工资料。
- 每次运行期DB连接复查路径/WAL别名与owner，并以mode=rw打开；DB移除不重新建库，外库替换/sidecar异常拒绝且原目标不改。23项schema/文件保护用例与全量回归已通过。
- BFF握手deadline修复并与请求取消组合，SSE不被普通5秒握手deadline截断；实际静默SSE超过5秒后仍存活，再退出并验证upstream取消。
- 旧身份/static/direct-proxy/适配smoke代码已退役；显式运行示例、schema权威和HANDOFF已更新，历史41覆盖替代关系逐项记录。
- Ruff 28文件格式及规则检查通过；自有8个TS/TSX解析通过；plist与browser脚本语法检查通过。解析/语法不是完整构建或浏览器验收。
- bind-b3逐文件核验325个冻结/候选输入与UI补丁；B3-EVIDENCE.json记录当前运行源码集合与日志哈希。完整构建/compiled/Chrome仍PAUSED。

## 历史产品裁定未决（c3时期，现由v1.1取代）

TRK-01/02本地夹具保障继续补证；TRK-03同代去重/正文补全/真实订阅备注可验证。C-01全量发布时间跨页倒序、C-03全量评分复合来源/分页、C-05跨generation公开折叠仍BLOCKED。保留冻结latest接收时间语义，不用前端页内排序冒充全量。转推/回复/引用与保留期未确认，保留历史候选规则，不宣称新版定稿。媒体/互动/重要标记仍未知。

B2 ingest/tracking=501，不改Projects、不伪造receipt，观察outbox保留pending可查询。真实平台/Watch/付费/凭证、正式收件/公网/生产未验证也未执行。

## 既有构建与验收记录 · 2026-10-16

既有重任务批次按同一主锁完成；最新build-9、source/compiled入口通过，327文件绑定一致。89 pytest通过，其中1个wrapper内7个Node项不重复计数。真实Chrome两尺寸11组完成，8通过、3组认证阻断，关联5个认证500，整体exit2/PARTIAL，pageerror0。实际Next停机后持续入库并重启查回通过。上述记录不代表当前重任务放行。

修复Tracking自建Auth singleton（改用冻结events/stream）及PATCH后刷新被丢弃导致旧revision409；新增有界合并刷新/页面响应fence与回归。代码f8e8f9101dbbe6e85d20847cd10c7d3eddffbd30，源集合8bc839b2aa8dd838d50560bb6e74cea6aa053eb784ab7934d8e61b85fd31c87d。认证依赖仍500，Auth/Projects固定源码未改，见AUTH-NEXT-BLOCKER.md。

最新政策product-decisions-v1.1固定50ee277aed435a723aab6139bd952e709b3ad08e：D1原创与引用任何对象显示；回复/转推/未知隐藏；D2十五天先备份清理+持久小账本；D6/D7/D8已定但语音held。C01/03/05方案已批准，不再待产品裁定。精确协议单独提交4e0b293901c72df0c28180eb849a2d67d8c9c4c9，仅proposal，尚未实现；C03需双方协议SHA冻结。当前回执以B3-REVIEW.md/B3-EVIDENCE.json为准，历史暂停/失败保留，不回写伪造成功。

## 当前资源约束 · 用户最新转达

上级总管Claude明确要求仍暂停完整构建和Chrome，集成窗口正在生产构建和部署。当前只整理代码与证据、跑必要轻量检查；等待项目总管或Claude通知解除后再做最终构建和浏览器验收。本轮只更新交接文档、核对既有证据与源码哈希，没有启动完整构建或Chrome。

## 夜间自主实施 · 获准继续

579a57f夜间批准及967f309认证依赖、0e2c86f C03冻结审查取代暂停。固定Auth f097与Projects aa51；先真实Next6种303/401、5种SSE撤销通过，再实现v4协议。R1/R2/R3按总管独立复现直接修复；旧失败（含TOCTOU 121/122）全保留。侧车改一次lstat；永久账本/过期回拨/分批清理/新路径恢复均有回归。本轮最终轻量127通过，2 wrapper内14 Node不额外累加。整个最终重任务批次仍使用原唯一heavy lock。

接线增量8b84ee97a94bae28e98b550b2721991f30088486由集成在core freeze后保留Projects全局SSE并加Tracking专用alias；本窗口按原候选路径验收，不重复改UI或做语音。当前交接以NIGHT-HANDOFF/NIGHT-EVIDENCE为准。
