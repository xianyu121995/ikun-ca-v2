# Hunter B4 本地交付报告 · 2026-10-16

已实现，待总管按最终提交源码审查冻结。没有合并、推送、部署或连接真实来源。实现完整SHA以本批Git HEAD及交付短报为准；逐文件hash/命令见 python/docs/b4/night-receipt.json，最终连续运行证据见 python/docs/b4/final-batch.json。

原实现基线 bd69bbd0bba6fdc4f7c66191a839612dd53989d6；放行63e8a2857241c6a76226f21435e40db9736a1e7e；协议b16fb36a8b8269350319c02a60faa6ea2708d95a；批准579a57f2e3e470525eb53f9f1f85ba75d25f3728；产品50ee277aed435a723aab6139bd952e709b3ad08e（product-decisions-v1.1）。只写Hunter代码/schema及隔离hunter.db；12个保留UI文件未动。他模块只以固定Git对象读取。

## 实现与文件

- python/hunterradar/{engine,providers,parsers,store}.py：原独立引擎/聚合/CRUD上增量适配，未另建引擎。≥5000 WSS、<5000 REST3600秒最新20条、未知pending；ACK与来源心跳分离，generation/baseline、并发隔离、预算/429、billing_unknown和恢复持久化。方向为Hunter主动关注Target，原始事件和个体归因不出普通DTO/SSE/日志。
- python/hunterradar/{protocol,formal,formal_api}.py：可信B1身份、固定scope/方向token、正式DTO/ETag/UUID幂等/游标/错误。C04 PATCH只写原研究模型，返回最小{discovery_id,revision,saved_at}；同库事务保存研究/revision/审计/幂等/脱敏事件，回执不存研究全文。正式模式关闭旧私有入口。
- python/hunterradar/{migration,retention}.py、schemas/hunter/001/003/004_*.sql：显式唯一迁移，原2及校验和保留；schema4解耦outbox外键，稳定ID永久小账本，七天微秒边界/持久时钟/60秒清理；online backup先成功再删。损坏副本也有限保留，只留小失败记录。恢复新路径，要求受控离线最新源，合并ledger/posted/回执/额度/SSE序号栅栏，不能复活或盲POST。
- python/hunterradar/__main__.py、src/main.ts：init/migrate/restore显式命令，Node24 execve唯一Python进程。serve/readiness不DDL；正式job不依赖cwd .env，compiled入口强制外采关闭，受控内部回执独立开关。health明确“未连接真实来源”。
- python/integration/website/**：真实BFF、页面、Action、controller和Hunter SSE贡献候选。固定UI只作最小回调/权限/错误/保存接线补丁，公共组件与原UI/CSS来源不改；host CSS仅解除脚手架main的760px限制。原services/hunter-worker/ui不归此实现。正式收件由集成在冻结后执行。
- python/tests/test_retention.py等、scripts/*b4.py、integration/tests/**、docs/b4/**：隔离夹具与证据。preview-only Action probe绕过Proxy验实际Action，不映射正式网站，不交付临时账号/数据。

## 实跑结果（分别计数，嵌套/历史不累加）

| 验证 | 结果及证据 |
|---|---|
| Python全量 | 227 passed，docs/b4/python-night-final.xml；含原130项，130已包含历史69，不另相加 |
| B1真实入口函数/Route Handler | 10 passed，auth-route-night.tap；与Python独立。CSRF/Host/伪造头/强制改密/禁启用/轮换/过期、SSE撤销/cancel、跨Request实现桥接、PATCH原始JSON保留 |
| TypeScript/noEmit、补丁apply check | PASS；固定B1/UI加controller/Route Handler/page/Action。production Next完整构建另见build-night.json/txt |
| 正式Next+B1+Hunter浏览器 | 14组，browser/results.json；112条合成发现跨100游标，真实研究回执/刷新/丢ACK同key/409草稿，管理/确认，实际Action绕过Proxy匿名401/user403/错CSRF403/超管202，静默SSE撤销，1440/390截图 |
| 原私有候选兼容浏览器 | 11组，legacy-browser/results.json；仅兼容保障，不充正式API验收；390/768/1440/1920/2560 |
| 后台进程与CLI | 3次主OS启动，Node24 execve→Python、TERM、SIGKILL租约恢复；另1个事务中途exit77子进程，不算第4次服务启动。研究/原key/cmd/evt/body/hash持久，init/migrate/restore、过期不复活，process-smoke-night.json |
| 外采门禁 | compiled入口拒绝外采=1，exit1且不创建DB；私有无.env cwd，release-preflight.json |
| 最终同源码连续批次 | final-batch.json核对运行前后hash相等；全批持唯一heavy lock，receipt见final-batch.json及night-receipt.json |

Python保留1条Starlette/httpx TestClient弃用警告，未为消警告新增依赖。冻结依赖锁不变。Next构建固定Auth f097与Projects cc95，页内实际执行批准的projectsAuth constructor策略；没有把未运行的Projects业务事务算通过。

## 裁定与总管回归

| 裁定/问题 | 本地结果及限度 |
|---|---|
| DEC-C04 | 字段边界/null/日期关联、并发/回滚/UUID、权限/If-Match/回放、过期旧key最小结果/新key404；真实保存刷新/Action guard。不注册canonical、不自动发监控 |
| DEC-D3 | 七天前1微秒/恰好/之后，编辑不延TTL，网站关闭照常调度；SQLite真实deadline注入、失败中断不删、损坏校验、3份/48h及CLI新路径恢复。满盘为OSError夹具，未破坏宿主磁盘做真实满盘 |
| DEC-D4 | 停用前已受理历史原72h计数，恰好包含、之后退出；停用/旧代在途丢弃，恢复baseline；同一稳定Hunter重放不凑两人 |
| DEC-D5 | 稳定Target永久极小账本无Hunter归因/研究全文；改名/乱序/跨代/窗口再达标/七天清理/重启/恢复不再首次发布；未知ID不造键，歧义迁移回滚 |
| B4-R1 | confirm A→PATCH B→最新ETag/新key confirm B=409；原A可返回原cmd；原cmd/evt/body/hash不变。test_confirm_then_research_cannot_reconfirm_changed_draft_as_original |
| B4-R2 | 恢复合并当前public_changes及sqlite_sequence高水位，含已删空洞/命令共享流；清旧内容而不复用序号，旧Last-Event-ID收到新号。test_restore_never_reuses_discovery_or_command_sse_sequence |
| B4-R4 | 受控非hunter.db临时文件合全部栅栏、checkpoint/校验/fsync后才独占新路径原子发布；真实SIGKILL 5边界，4个发布前拒激活、发布后保888账本无新提醒。restore-kill.json；临时副本亦3份/48h |
| B4-R3 | WSS/REST前跳4天再回拨，过期观测不烧永久首次提醒键；首次窗口/aggregate/DTO同一有效时钟。test_clock_forward_then_rollback_never_burns_first_target_alert（两来源） |

## 原P0及未验证项

HUN-01/02/03/04、AUTH-01/02/03、ISO-01、OPS-01在本地夹具/本批实际入口范围PASS。PRO-01只证明固定B2模型与Hunter确认/回执边界，未运行真实ManagedProjectsIpc事务、B3命令和600名额整链。TRK-01/C0整链、独立OS低权限账号隔离、真实来源、OPS-02正式上线仍未验证，归总管/集成门禁。本窗口没有部署权限，ready/ACK/202不冒充connected/running。

REST最新20条可能漏历史/断档；首次观察不是可靠follow时间。WSS缺可靠外层关注时间拒绝，不以profile.createdAt填假时间。缺可靠关注时间政策本轮未定，仍按原已验证来源策略披露。signals仍是当前72h合格列表，发现GET可留七天，不偷换列表profile；UI排序限当前服务器页，跨页用cursor。D1/D8已确认，语音不在B4实现。

## 失败证据与修复

旧轻量阶段68/1、112/1、118/1、Node6/2及离线cache/本机socket权限失败保留在原记录/锁receipt，不当成功。旧Next跨Request私有状态故障以显式字段重建修复，对应Node及真实Next通过。

夜间首次125/5（旧版本/未放行断言、无稳定ID夹具），随后129/1（遗留版本断言），增量209/1（仅账本恢复目标未提前阻断）均修正；坏副本48h清理曾218/1，修正不能以修改mtime延寿后最终227通过，保留python-night-backup-age-failure.xml。恢复编辑曾缩进错误导致import失败，对应锁receipt保留，未算浏览器执行。

正式浏览器先有“旧第一页变化误作游标完成”和未等自动聚焦造成测试字段串写；failure截图/JSON在browser/attempt-*，修正状态/网络等待后14组通过。R1/R2/R3均已直接修复并纳入最终227和同源码批次。UI误发时取消过排队验收(exit130)，夜间批准后才继续API/接线验收；未修改原UI。

## 运行与收件

精确依赖SHA、源路径→正式映射/补丁、SQL/hash、Node/Python入口与锁、无.env私有job cwd、外采关闭/内部回执开关、init/migrate/restore及BFF/SSE门禁见python/integration/README-B4.md。只能由集成在总管冻结后按清单收件；不整包收preview、probe、临时账号、var、DB、密钥或缓存。原轻量报告保留为docs/b4/report-light-history.md，其hold/pending表述仅属历史。

路径稳健性补充：按总管静态建议改为每候选单次lstat，正常sidecar消失容忍，主库仍须存在，软硬链/私密权限继续拒绝。新增2条回归通过；这是预防性修复，未声称现场复现故障。R4后隔离测试曾223/1（旧断言只允许hunter.db、不认识受控tmp），收紧为自有根内hunter.db或精确tmp格式后最终227通过。

最终最小接线补正：live X主页以规范handle构造https://x.com链接，noopener/noreferrer；live站内导航保留默认href（只有demo拦截）；C/D评分显示、选中及保存保留均已在真实浏览器验证，未猜成未评分/运行态。集成后续/api/v1/hunter/events别名及SSE刷新遵8b84ee97a94bae28e98b550b2721991f30088486另验，未计入本候选浏览器成绩。
