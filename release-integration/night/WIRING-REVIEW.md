# SSE / command / relay 最小接线只读审查

状态：方向可行，有明确接线差异；只读准备，尚未实施或验收。基线`f7933f0d64f83f02f4274ea434e8a919f482b4c6`。路径、输入快照与未来文件清单见`wiring-files.json`。不将未冻结工作区字节登记为accepted依赖。

依据：总管本次技术裁定、phase2 API第90/92行的原command_id链，以及夜间授权`579a57f2e3e470525eb53f9f1f85ba75d25f3728`。总管仍需把两个增量公开路径及精确接收差异记入版本化协议/收件记录；本窗口不改冻结全局接口或机器清单。

## SSE

| 对外路径 | 唯一handler | 原生id / 恢复 |
|---|---|---|
| `/api/v1/events/stream` | 现有`projectEvents` | numeric sequence；原有`Last-Event-ID`校验/重放 |
| `/api/v1/hunter/events` | 最终获验收的`hunterEventsRoute` | `hunter:N`；原handler解析并读取自身sequence |
| `/api/v1/tracking/events` | 最终获验收的`trackingEventsRoute` | `evt_ID`；原Tracking通过本库定位恢复位置 |

两个新增route只委托本模块handler，固定Node/dynamic，不改id、事件type或payload，不拼接或互译cursor。分别保留B1建连、逐数据块和安静流撤销，以及原重放/无重复提醒语义；原生无效/过期cursor按原handler错误处理，不通过切换来源或清空cursor假装恢复。handler内部已有的转换保留，不由新route重写。

当前直接冲突是：Projects已占全局stream；Tracking候选也把它导向Tracking；Hunter预览脚本生成同名Hunter挂载。后两者的全局挂载不能收进正式站。Tracking live当前确实使用全局URL，应改为本模块URL；Hunter当前未冻结controller只有读取/刷新，未发现EventSource，不能宣称“替换URL即完成”。Hunter live订阅/恢复行为需要先由owner交付可验收版本，或在总管明确的最小接线范围内另收增量，不在本轮补写。

**B1门槛是具体阻断。** 当前B1 readApi只认可原stream，两个新路径对user会先403；仅新建Route Handler不能解决Proxy前置拒绝。最小接法是经批准在网站`projectsAuth()`已有只读规则增量中增加两个精确正则，继续使用已验C03/cc95的同一store与当前实例constructor。现有Proxy已调用`projectsAuth()`；两个新route也应先调用该准入，再委托`withAuth` handler，保证不经Proxy的入口同样受控。不得由某个worker重建Auth singleton、扩大为整个hunter/tracking前缀或更改B1源码。C03 helper的域源hash仍保留，接收端两条规则需单列批准delta及目标hash。

## Command gateway

保留唯一`GET /api/v1/commands/{原cmd_ID}`作为网站gateway，B1验证真实身份/固定scope，逐域使用既有服务凭据/IPC。command_id先按协议校验且全程不变，不信浏览器提供的owner/role。

- Projects经既有`operation=command`查询canonical映射/持久outbox投影；未映射时委托Hunter已有命令投影，允许project_id/subscription_id为null。
- 有Projects canonical后查询Tracking同一cmd的实际投影，不因Projects先返回200/pending而短路。直接Tracking命令也必须可查询，不能只保留Hunter来源分支。
- 仅确切的`404 + NOT_FOUND`可作为该来源未找到；401/403、超时、503、错误scope/投影不匹配均不能当404。可确认归属的成功投影不应被无关worker不可用拖垮；无法确认的结果保留unknown/不可用，不能编造NOT_FOUND或running。
- Tracking尚未接收而Projects已持久排队时，只报告实际pending；读取gateway不重新确认、不分配新cmd，也不为查询触发新的投递机制。accepted/ACK与真实running/connected分别保留。

当前站route仅委托Projects。Tracking候选是“Projects明确404再查Tracking”，因此漏Hunter待映射，而且Projects200时未查Tracking实际状态；Hunter预览单来源commands挂载同样不能覆盖全局route。所需变更是全局gateway的小范围组合，不是重写领域命令状态机。超时预算、各来源错误与canonical一致性按最终冻结handler签名形成精确接收delta。

## Projects → Tracking relay

复用原`relayOnce`：`outbox_claim`租约 → send或按原cmd reconcile → `outbox_result`，继续使用既有Projects outbox与Tracking inbox。不写跨库SQL、不新建表、总线、job或公开relay接口，不把GET command当投递驱动。

**当前缺口：** 本站生产`start-c0-lite.mjs`没有relay调用点，现有`relayOnce`只在测试被直接调用。需在网站既有受托管生命周期内接入有界、单次在途的调度，配置缺失/Tracking不可用只影响该relay，停机时停止新轮次，进程重启仍由原持久租约/reconcile恢复。入口与可执行helper产物必须随冻结包核对；不能假定当前TS helper可直接被Node父进程import，也不能复制其业务或新起第四作业。具体调度文件在下表列为待总管确定的接线位置。

## 未来收件文件范围

| 目标 | 类型 / 边界 |
|---|---|
| `apps/website/app/api/v1/hunter/events/route.ts` | 新增薄delegate；经只读准入后委托Hunter handler |
| `apps/website/app/api/v1/tracking/events/route.ts` | 新增薄delegate；经只读准入后委托Tracking handler |
| `apps/website/lib/projects.ts` | 先精确接C03，再只添加两条获批只读规则；源hash/接收delta分别绑定 |
| `apps/website/lib/hunter.ts`、`lib/tracking.ts` | 只接最终已验handler/helper，不在本轮合入或重写 |
| `apps/website/components/tracking-live.tsx` | 最终已验live的EventSource改本模块路径，保留原事件处理/恢复 |
| `apps/website/components/hunter-controller.tsx` | 最终SSE绑定仍待owner冻结；当前不是单纯URL替换 |
| `apps/website/app/api/v1/commands/[id]/route.ts` | 唯一gateway的三域原cmd查询组合；不照抄单来源预览route |
| `scripts/start-c0-lite.mjs`或网站受托管服务端入口 | 待总管固定执行位置/编译映射；只调度原relayOnce，无新服务 |
| `release-integration/night/**`、自有接线/收件工具及测试 | 记录批准Git/输入/目标hash；覆盖三域并存、权限/撤销、原cmd恢复 |

原`apps/website/app/api/v1/events/stream/route.ts`及`lib/project-events.ts`保持Projects语义；`lib/outbox-relay.ts`机制、领域库/schema、B1领域源码、现有Auth/Projects readiness不因这次接线扩写。根协议/ownership/manifest的增量由总管记录，本窗口不自行改冻结文件。

## 收件后必须证明

三种stream并存、跨类型cursor拒绝且不串源；匿名401/user GET200/普通用户写拒绝；直接handler及Proxy都受B1保护；禁用/改密/退出/角色变化/静默流撤销和上游取消；重放不重复提醒；Hunter映射前/映射后/直接Tracking原cmd查询、错误不降格404、单worker故障不拖垮不相关读取；既有relay的未知结果reconcile、网站重启恢复及重复inbox幂等。测试时仅合成隔离数据；完整Next/浏览器按唯一heavy lock。

本轮只有文件/代码静态核对，没有执行功能测试、构建、网络调用、数据库访问、合入worker、服务启停或部署；没有对B3/B4实现作通过声明。
