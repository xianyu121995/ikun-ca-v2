# B4 轻量阶段记录（未交付验收，尚未提交新 commit）

基线 `bd69bbd0bba6fdc4f7c66191a839612dd53989d6`，原 `codex/hunter-worker` Worktree。放行包 `63e8a2857241c6a76226f21435e40db9736a1e7e`。本轮处于代码及轻量非浏览器回归阶段；总管通知 C0-lite 优先，尚未收到解除重任务时段的明确通知。因此没有启动完整构建、依赖安装、浏览器、预览服务或 OS 进程重启批次，没有锁 receipt，不能据此验收 B4。

## 已实现的本地候选

- 沿用原引擎、Store、聚合、CRUD 和 provider，只增加协议/迁移适配。方向保持 Hunter 主动关注 Target；只运行合成夹具，未调用真实平台。普通 DTO、事件与日志不含猎手名单、个体归因或 raw payload；超管账号 API 只给必要管理投影。
- 4999/5000/5001 阈值和未知 pending；REST 成功后精确加3600秒，最近20条、满页/断档警示、防同账号并发重入、持久预算/429；计费不确定或进程中断的请求意图持久阻断自动付费重试。
- 新/恢复/切换 generation 的 WSS 基线在订阅 ACK 后建立，ACK 不冒充来源心跳。旧代在途结果隔离；稳定 Target ID/handle alias 保留同一发现 ID，冲突不合并。72h 阈值、重放和再次达阈值只保留一条发现；缺时间/删猎手历史仍保持已验证口径，不宣称待定政策已获批准。
- 正式模式关闭旧私有 API/页面与本机免密回退。固定 ikun-main，独立方向 token，网站 B1 刚验证的 actor；标准 DTO/envelope、UTC/null、ETag、UUID 幂等/七天以上保留、绑定条件的数据库 keyset cursor。未知内部 commands/subscriptions 返回501。
- 人工 confirmed 请求原子保存项目快照、发现 revision、审计、幂等结果、原 cmd_ID/evt_ID/outbox，冻结事件名 hunter.monitoring_requested。Projects 唯一返回 canonical，Hunter 不直接操作 Tracking 或主页。丢 ACK/崩溃后查询原 evt_ID 回执，校验 event/command/project；已 POST 而404的回执保持 unknown，不盲重发。Projects 受理后对外仍为 pending，不能证明远端运行。
- 显式 init/migrate 是唯一 DDL 入口；serve/readiness 不建库。schemas/hunter 为 SQL 权威，保留 foundation1/原2，增量3；兼容三/四列 ledger、独立 checksum registry、显式 INSERT 列、失败回滚、未来版本/错校验和/路径别名拒绝、0600/0700、备份新路径。旧未定协议 outbox 保留原文并进入人工核对，不改写旧 ID 或冒称已迁移为正式事件。
- BFF/页面/Action、SSE贡献、控制器和定稿 UI 最小补丁只放 Hunter integration 候选。没有修改其他窗口、正式 apps/website 或公共 UI。C-04 研究保存正式接口仍501/按钮禁用，提案见 B4-C04-PROPOSAL.md；人工确认随附完整 ProjectFields 是既有冻结接口，不是新增独立研究保存机制。

## 验证与覆盖映射

最终实跑计数见 `python/docs/b4/receipt.json`、JUnit 和 TAP，不把历史成绩相加。轻量 TypeScript 检查含冻结 UI/B1 与本批 controller、Route Handler、页面、Action；这不是 Next 完整构建或浏览器验收。

原69项 Python 保留覆盖；两项旧 v2 确认测试改验冻结事件/回执；原“跨来源不同稳定目标 ID 仍拼成发现”改为冲突拒绝；foundation 测试改验增量3；夹具显式 init、已建立基线并固定毫秒时钟。旧私有 API/签名/浏览器仅是兼容历史保障，不能充正式 API 验收。

新增测试覆盖迁移兼容/回滚/权限/校验和/恢复、别名和 generation、实际 B2 固定序列化模型（S/A/B/C/D/null 六项已含在 Python 总计中）、正式 API 权限/幂等/分页、回执丢失/错回执/不重发、billing_unknown/429/ACK与心跳。8项 Node 测试独立计数：实际 B1 模块和 Route Handler（绕过 Proxy）验证匿名/user/CSRF/伪造头/强制改密/禁启用/重置/本人轮换/七天过期、SSE帧/续传/静默撤销/cancel、失败不回退演示。Auth 合成测试库只由固定 B1 模块操作，Hunter 实现不直接打开 Auth/Projects/Tracking 库。

已保留失败事实：早期目录夹具0755被拒（68通过/1失败）、旧断言期待401而新规范503（112通过/1失败）、原浮点时钟转ISO微秒舍入造成边界夹具偶发失败（118通过/1失败）；均修正夹具/断言后复跑。Node 首轮6通过/2失败是测试调用错误的 B1 fixture 方法名，改为固定源码真实方法后8项通过。Starlette/httpx 一条弃用警告保留，未新增依赖。

| P0 | 当前状态 | 证据及限度 |
|---|---|---|
| HUN-01 | PASS（本地） | 方向、错账号/畸形、字符串 content、脱敏；真实方向采用本轮用户已实测决定，本窗口未重验真实平台 |
| HUN-02 | PASS（本地） | 阈值、pending、3600秒/20条、并发/预算/429；未证明真实平台无限历史覆盖 |
| HUN-03 | PASS（本地） | 72h边界、不同稳定猎手、重复/重放、单发现/别名冲突、generation；待定保留政策未另行实现 |
| HUN-04 | BLOCKED | 轻量恢复/重连/回执夹具通过；本批三次 OS 启动/TERM/KILL尚未复跑 |
| AUTH-01/02/03 | BLOCKED | 8项真实 B1/入口函数轻量测试通过；页面/Action/1440/390浏览器运行未验 |
| TRK-01 | BLOCKED | Hunter→Projects 回执边界夹具通过；B3最终SHA、600名额满及实际 NEW_TWEET运行不归本批夹具证明 |
| PRO-01 | BLOCKED | 实际固定B2序列化模型兼容；本窗口未运行 Projects事务或跨worker全链路 |
| ISO-01 | PASS（本地边界） | 实现仅 Hunter writer/SQL，路径与软硬链接拒绝；跨进程整体仍待C0 |
| OPS-01 | BLOCKED | B4 新 OS smoke脚本已准备但未运行，不引用旧三次启动当本轮证据 |
| OPS-02 | BLOCKED | 旧版/Watch/生产/域名均未动；测试域名与正式发布未获本窗口授权 |
| C-04 | BLOCKED | 仅提案，未发布研究写路由 |

## 继续验收的门槛

1. 总管明确解除 C0 优先时段，完整构建、浏览器和整个预览生命周期才使用主仓库同一个 `scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- <前台命令>`；保存实际 receipt，不能另设锁或仅锁启动瞬间。
2. 固定依赖的 Next 完整构建、1440/390真实浏览器和新OS smoke必须实际运行。原11组私有浏览器与3启动的保障分别映射到兼容历史组/正式页面组与 process_smoke_b4.py；没有运行就不记 PASS。
3. C-04 等待总管裁定；原API/DTO/共享枚举不修改。公共 commands/SSE 的最终多来源汇聚、正式接线/收件归 C0，当前预览只能验证 Hunter贡献；不能整包收件预览候选。
4. 通过适用门槛后再白名单暂存、原hook前向提交；不提交保留 UI、数据库、凭据、var 或构建产物。原未跟踪 UI 十二个文件 SHA 持续核对，未修改、未暂存或清理。无 merge/push/deploy 权限。
