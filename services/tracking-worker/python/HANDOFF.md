# B3 候选交接 · 代码与轻量证据

**状态：B3 本地候选；最终完整构建、compiled launcher、Chrome 验收暂停，未申请整体通过。** 用户转达上级总管 Claude 的最新通知：集成窗口正在生产构建/部署，继续暂停完整构建和 Chrome；本窗口只整理代码/证据、跑轻量测试，待明确解除。不得因锁空闲自行恢复。

本分支 `codex/tracking-worker`，父基线 `9e2835cafc95cb15dc4b8178abacf0c604018536`。仅修改 services/tracking-worker 与 schemas/tracking。未合并、推送、部署、修改其他 Worktree/共享契约/根依赖；不停止旧服务、不修改旧Watch、Tunnel或生产库。

## 固定依赖

| 输入 | 完整 SHA |
|---|---|
| phase2 spec | 9699375c920465b5d802e7acff17b5421203e544 |
| B0 runtime | 85be3bd6dce25d82033b6cb1a7157aaa39bd571e |
| B1 Auth 源码 / 审阅 | 28e6aaf4141790fc74ae4ae4429be4b854460955 / c0f86bc20fc7b3ca147da863759b98acced8de44 |
| B2 Projects 源码 / 审阅 | d0fdefab2aa230ebb8df856aed306d0184d362e2 / ad4d5df91450a735465d21142ffc3e26536e948a |
| 公共 UI | 486294ac3255b08fdb13a307ee15f96c571020d9 |
| Tracking UI | d90598f4bc595458ce26c5ee1c2e1618e318abc0 |
| B3 放行 / 产品增补 | 9e1d1aa53d58b9ee4f23f5ec1356da0ebbf1e362 / c3f535b0342253a74905b65ea87bd9b819624061 |

其余冻结输入及哈希在 integration/prepare-b3.py、B3-EVIDENCE.json。依赖按Git对象导出到本模块忽略的 `.b3/preview`，无merge。bind-b3.py逐文件核验325个冻结/覆盖输入、选择性B2文件与固定UI补丁；不能用其他窗口HEAD代替冻结输入。

## 已实现

- 固定 B2 CommandEnvelopeV2、方向 Bearer、scope/actor/operation 校验；事务 inbox/hash/sub_ID/审计后202，8字段结果；并发重投同ID只一条，异body409，ACK丢失按原ID查询，数据库故障503不假404。
- 人工 confirmed 加入、启停/恢复/移除。desired/observed/operation/connection分离；远端完整回查才成功，600名额只报错不淘汰。保留稳定sub_ID、revision/generation/baseline、ownership和重试时间；过期任务不发起远端写，外部flags变更不删除。
- WSS ACK/pong、断线重连、REST最近100恢复、同代去重/正文补全、重启恢复；未知发生时间保留null，超窗possible_gap。网站退出后独立引擎继续采集。
- SQL权威迁到schemas/tracking。显式init/migrate，runtime/ready不DDL；三/四列ledger兼容、独立checksums、future/name/hash/结构/唯一索引/别名检查；失败回滚。旧数据/seq/receipt与tweets_legacy保留；非空旧身份/无法映射ID停下待审。
- B1实际Route/Page/Action guard与SSE持续撤销。Worker不接人类Cookie/登录，不保存会话，不读其他库。已退役旧静态登录、session getter、直接反代和旧smoke入口。
- 固定UI的最小live controller/补丁、真实API、备注在前、账户管理、真实命令状态、订阅分页/动态游标、只读权限；单AppShell、批准导航名。此项源码已实现，当前源码Chrome尚未验收。
- tracking.activity.created与标准SSE持久事件；观察outbox保持pending可查。B2 ingest/tracking=501，未发投递请求、未伪造receipt、未改Projects收件实现。

## 验证口径

本轮精确日志/文件哈希与分组计数在 B3-EVIDENCE.json。运行说明见README；所有远端用例为MockTransport/loopback，真实provider调用为0。

| 范围 | 证据与限制 |
|---|---|
| 后端/实际B1-B2入口全量 | pytest最终轻量日志与JUnit；1个wrapper内部6个Node测试只计一次 |
| 实际B1入口 | 匿名/普通用户/强制改密/伪造身份、Host/Origin/CSRF、页面/Action直接guard；旧getter虽200仍不能授权业务 |
| B2链路 | 固定B2真实Service序列化+relay，POST后ACK丢失再GET原ID；无额外内部幂等/If-Match头；Projects数据经API比对不变 |
| SSE | 标准envelope/replay；超过普通请求握手deadline仍持续；退出后静默流取消并验证真实upstream关闭；禁用/重置/绝对7天/轮换旧Cookie业务拒绝 |
| 生命周期 | 实际网站fixture退出后仍收推文；引擎崩溃/租约过期重启不重复；当前Node24源码入口SIGTERM=0、父SIGKILL私有树回收/重启通过；非compiled证据 |
| 静态检查 | Ruff、TS解析、plist语法、git diff/hygiene；TS解析不等于完整类型检查 |
| 完整构建 | 第一轮build-1通过，但源码后来变化，只保留历史；不得计为最终构建 |
| Chrome 1440/390、compiled service.mjs | 已准备新测试入口；最新源码未执行，等待资源暂停解除 |

唯一测试提示是Starlette TestClient/httpx弃用警告，无测试失败。最初普通沙箱禁止127.0.0.1 bind导致两个WSS用例环境失败，随后用私有loopback权限复跑通过；其他首轮失败与修复日志均保留，不覆盖。

## 原41项覆盖迁移

历史9e2835c的41是旧候选报告，不叠加到新计数。26个引擎/远端用例保留（仅WSS未知时间改为保留null）；1个进程用例改用新内部协议；2个schema用例扩为显式迁移/兼容/回滚/损坏/别名测试。旧8个API、2个身份getter、2个v1/lease覆盖由新方向API、B1实际入口、command/sub映射、public PATCH与lease测试替代。旧独立登录/模拟getter/static页面的成功用例退役，新增旧入口404与旧身份写入拒绝。旧Chrome/BFF/adapter/launcher成绩不用于本B3验收。

## P0 与阻塞

| 项目 | 当前结论 |
|---|---|
| TRK-01 | 本地远端夹具通过：ACK假成功、配额600、超时已执行/未执行、回查仍未知、重启核验；真实平台未验收 |
| TRK-02 | 本地停止失败/noop/超时不假停止，恢复同sub/generation、竞态保护通过；UI点击待Chrome |
| TRK-03 | 本地同代去重/补全/重放、反序发布时间/接收时间、null、跨页及跨代夹具通过；备注真实来源已接，视觉位置待Chrome |
| AUTH-01/02/03 | 实际B1业务入口与撤销证据通过；本模块Chrome待验收，不能当全站通过 |
| ISO-01 | Worker只写本库；经各owner API的私有集成夹具验证移除不改主页；未检查其他worker生产 |
| OPS-01 | 本模块网站独立/源码guardian恢复通过；最终compiled入口及三服务全站恢复待总管 |
| OPS-02 | 无部署/旧资源变更；域名与生产验收未执行 |
| C-01 / C-03 / C-05 | BLOCKED：全量发布时间跨页倒序 / 全量评级组合来源分页 / 跨generation公共折叠未裁定；保留冻结DTO和接收时间语义，不静默改规范 |

转推/回复/引用与保留期待定，历史过滤候选不是产品定稿；不新增清理。媒体/互动/重要标记缺来源保持未知，禁用虚构控制。观察收件501、真实独立账号/配额/Watch隔离、公网/生产/跨worker完整链路均未验收。

## 解除资源暂停后

同一主仓库with-heavy-lock.py包住最终串行build-b3.py，以及新Chrome整个预览生命周期；compiled生命周期也绑定同一最终构建。重跑失败项并保留日志，绑定最终源码/输入/构建ID/截图/锁receipt后提交总管审查。已知历史锁receipt：`ikun-ca-v2/var/coordination/tracking-worker-a11a80a1-a2ab-4200-a5cc-16e3c32bfbfb.json`，仅对应过期第一轮构建，不能冒充最终锁收据。

当前无生产服务变更或后台驻留候选。配置/DB/venv/依赖/测试截图/运行日志保持忽略；不清理旧库/旧配置，不用旧二进制覆盖v3库。收到总管退修后继续前向修复，不rebase/reset/amend/force-push。
