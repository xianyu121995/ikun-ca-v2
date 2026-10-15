# B3 当前交接 · 2026-10-16

**本地PARTIAL，未整体签收。** 未受影响的跟踪业务回归及两尺寸浏览器流程已完成；认证Next组合500仍BLOCKED。新版产品已裁定，D1/D2/C01/C03/C05仅提交精确协议，待总管/Projects共同协议审查后实现，不能报新DEC通过。

**当前资源约束：完整构建和Chrome继续暂停。** 用户最新转达上级总管Claude，集成窗口正在生产构建/部署；本窗口只整理代码与证据、跑必要轻量检查，等待项目总管或Claude明确解除。下列构建/浏览器回执均是既有已执行记录，本轮未重跑，不代表最终验收放行。

- 原候选：`2c7ce9a36350aa438c8d197b60d41de2b4aa1c96`。
- 协议提案：`4e0b293901c72df0c28180eb849a2d67d8c9c4c9`，`../B3-FEED-v1-PROPOSAL.md` / `.json`。
- 本轮受测代码：`f8e8f9101dbbe6e85d20847cd10c7d3eddffbd30`；源集合SHA256 `8bc839b2aa8dd838d50560bb6e74cea6aa053eb784ab7934d8e61b85fd31c87d`。
- 当前详细回执：B3-REVIEW.md、B3-EVIDENCE.json；认证阻断：AUTH-NEXT-BLOCKER.md。原暂停检查点保留在2c7ce9a及忽略的artifacts/b3/history，不覆盖失败日志。

## 完成内容与范围

只改 `services/tracking-worker/**`、`schemas/tracking/**`。独立引擎/本库/服务方向API/命令inbox/真实远端读回/600名额/恢复与既有回归保留。新增修复：前端一次活动读取加一次合并后续读取，修改后等待新revision；不会因已有刷新而丢弃请求。SSE改用冻结events/stream，Tracking不再重建B1认证singleton。UI仅最小live补丁，无公共CSS改造。

未改其他Worktree、根契约/依赖、Auth/Projects源文件、共享Watch、旧服务、Tunnel或生产数据；未merge/push/deploy。仅固定Git对象导出到本模块忽略的preview；未使用浮动分支。真实provider调用为0。

## 测试与证据

| 项目 | 实际结果 |
|---|---|
| pytest | 89/89；1个wrapper内7个Node子项，不能再加7 |
| 固定B1/B2 Node实际入口 | 角色/CSRF/直接page与action、真实B2序列化relay/丢ACK、SSE/replay/撤销、公共命令回查、刷新队列7项通过 |
| 构建 | 最终build-9串行5步通过，327文件前后核验一致；Next BUILD_ID JzEPmMz6lFoVlV1ziEm9_ |
| source/compiled生命周期 | 显式init、SIGTERM=0、父SIGKILL私有树回收、重启通过 |
| Chrome 1440/390 | 11组执行完，8组通过、3组因认证阻断；跟踪业务通过、pageerror=0，整体exit 2/PARTIAL |
| 网站独立 | 真实Next退出后新推文继续进入本库，Next重启后查回，重复推文仍去重 |
| 静态/视觉 | Ruff通过、Git hygiene通过；两截图实际查看、备注在前、无横向溢出，窄屏按冻结UI隐藏媒体栏 |

浏览器真实验证项目创建确认、ACK假成功后unknown、实际核验成功、编辑→停止→恢复、移除不改主页、推文去重/刷新持久、只读业务写403、安全原文链接。远端为MockTransport/loopback，不是6551真实账号验收。

最终重任务锁receipt：主仓库 `var/coordination/tracking-worker-ef5b34a1-602e-49a1-9cd7-044f1485eb4f.json`；完整复制及哈希在本模块artifacts/b3/heavy-lock-receipts和B3-EVIDENCE。exit2明确表示浏览器认证阻断；不是构建失败或全通过。

## 当前阻断与后续

1. AUTH-01/03：经过固定Projects/Tracking组合后，禁用账户/后续匿名请求出现5个认证500，预期303/401。无业务data泄露，不能算Auth通过。Tracking自己的认证重建已移除；保留固定B2/Auth字节，给owner提供隔离诊断与未应用修复方向。
2. `product-decisions-v1.1`（50ee277a…）已确认D1原创和任意对象引用纳入、排除纯转推/回复/未知，D2十五天及账本；C01/C03/C05方案已批准。4e0b293提案精确定义profile、SAB全量计数/游标/评级方向/迁移备份恢复，当前pending_protocol_review；C03还需pending_owner_implementation，不再等待产品裁定。
3. B2 ingest/tracking仍501；观察outbox保持可查询且pending，没有伪造receipt或代改收件。
4. D6/D7/D8均已定，语音继续held，未增加播报/开关/队列。真实平台、跨worker、公网与生产验收均未执行。

收到协议审查后仅按批准范围前向实现；不重写引擎/页面、不amend/reset/rebase。完整构建/Chrome当前继续暂停，明确解除后仍按主仓库唯一with-heavy-lock.py串行。运行命令见README；新profile/004迁移尚未实现，不能运行提案当作已交付API。
