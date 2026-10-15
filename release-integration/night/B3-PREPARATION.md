# B3 Tracking 冻结前接入准备

状态：`WAITING_ACCEPTED_FREEZE`。这里只准备新作业/库/私密配置与接线范围，不接收B3运行实现、不迁移、不构建、不启停或部署。已验B4网站/Hunter仍运行`75b81a2b5210e41bdf8522467c7fba2a6a6e693c` / `GEeQtBnxMYzLHcpnuweJS`，Hunter域源`10fe9d73dcf9d2dd296b808e8aaee41308f12112`；不因Tracking接入重启或迁移Hunter。

授权沿用夜间`579a57f2e3e470525eb53f9f1f85ba75d25f3728`、网站接线`8b84ee97a94bae28e98b550b2721991f30088486`及可选view hint补正`6ea8b004c368e17a123e055848f59f6370f2c29d`。只读参考B3交接文档所在Git对象`59e5286f605313b20a3ec0c7e976341f3ee6104e`，不把该对象视为核心验收冻结。cursor错误body超限取消的最后P2修复、最终bind/build证据待owner交付，不在本窗口代修。

## 独立路径与配置方案

沿现有私有根`/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite`，相对位置如下；本轮不在该根创建任何新文件。

| 项目 | 计划位置 / 要求 |
|---|---|
| 新job | `ca.ikun.v2.c0lite.tracking`；安装前确认同名作业及plist确证不存在 |
| 监听 | 仅`127.0.0.1:4012`；安装前核空闲，不能停止占用者 |
| 唯一库 | `data/tracking/tracking.db`，新库显式init；app-id `0x494B0202`、schema/SQL以最终冻结为准 |
| launchd cwd | `jobs/tracking`，0700、无.env；网站/Hunter cwd不改 |
| 私有env | `config/tracking.environment.json`，0600；只含本worker所需业务配置 |
| 私有配置 | `config/tracking/tracking.json`，目录0700/文件0600；Node→Python实际cwd可能为此目录，按最终包核对并如实记录 |
| 独立依赖 | `venvs/tracking`，按最终`requirements.lock.txt`创建，不复用开发或Hunter环境 |
| 冻结回执/计划 | `config/tracking.accepted.<candidate>.json`、`plans/tracking/<candidate>/`；全SHA/runtime/argv/executable/schema精确绑定 |
| 独立日志 | `logs/tracking.log`、`logs/tracking.error.log`，0600 |
| 回滚 | 仅卸载新Tracking job并归档其plist，保留库/日志；网站沿既有upgrade回滚配置与代码，不回写旧库 |

硬关闭外采：`remote_enabled=false`、`dedicated_account=false`、provider `token_file`为空，`IKUN_TRACKING_EXTERNAL_IO_DISABLED=1`；provider key/旧Watch/代理和隐式.env均不得继承。网站只新增既有方向的`TRACKING_API_URL=http://127.0.0.1:4012`及独立`TRACKING_API_TOKEN`，保留现有Hunter/Projects配置值；不是新增一种方向或token协议。Tracking不能收到Hunter token、Projects IPC凭据或Auth会话。

总管已只读确认Node白名单与Config.secret支持现有环境变量方向token，配置方案按本次裁定固定；不接收该未冻结候选的运行文件：

1. 正式计划固定精确冻结Node `dist/main.js`，其实际启动绝对`python/entry.py serve`；不使用无config的B0 fallback，也不使用预备工具中保留的旧直接Python模块分支。`IKUN_TRACKING_CONFIG`必须非空绝对路径且位于本root/config；实际Python cwd是配置父目录，launchd cwd与该目录均无.env。最终compiled hash、entry.py源hash、独立Python及owner预检仍必须与冻结包核对。
2. 固定`TRACKING_API_TOKEN`私密env方案；`service_token_file`、provider `token_file`、`admin_token_file`、`read_token_file`与旧`auth_session_url`均保持空。文档的file示例只是可选载体，不因此添加秘密文件、token机制或放宽守卫。

已按总管允许的窄范围补守卫：接受回执新增必需`tracking_config_sha256`；Node Tracking runtime清单必须含`services/tracking-worker/python/entry.py`并逐字节校验；配置父目录加入既有dotenv拒绝检查。源码`70f6c2bd4f72222432451c1bb05b1851d2c4074d`已获根`fa32db26ced86cc4338f1b5ea542e4518985b6ae`准备工具审查通过。原31项保留并新增7项，owner/总管分别复跑同一套38/38，定向9项不另加，见`tracking-guard-evidence.json`。B3核心冻结、显式迁移及最终release/Python预检仍必需；尚未部署，运行中的Hunter仍使用原75b release/原计划内的守卫副本。

部署receipt必须分别记录：网站新candidate、Tracking新candidate、保持原位的Hunter release75b及Hunter域源10fe。不能因网页升级就把Hunter作业记成新release。对现存Auth/Projects/Hunter做在线备份，Tracking意外已有库时先停准入核归属，绝不能覆盖或默认为可重建。

## 最小接线目录

| 目标 | 收件方式 |
|---|---|
| `services/tracking-worker/**`、`schemas/tracking/**` | 只在最终control明确放行后merge精确源码，逐项核源码/证据/SQL/依赖/compiled hash |
| `apps/website/app/tracking/page.tsx`、`actions.ts` | 按冻结清单中的实际文件名映射，保留B1入口与已批准布局 |
| `apps/website/app/api/v1/tracking/[[...path]]/route.ts` | 只委托已验BFF；不接probe/fixture HTTP入口 |
| `apps/website/lib/{tracking,published-feed,feed-casefold,coalesced-refresh}.ts` | 最终清单有才接，不照抄未冻结工作区 |
| `apps/website/components/tracking-{live,shell}.tsx`及owner UI补丁 | 固定UI `d90598f4bc595458ce26c5ee1c2e1618e318abc0`，先apply-check，再核输出hash；不改公共UI/CSS |
| `apps/website/app/api/v1/tracking/events/route.ts` | 将本模块未接入占位改为已验`trackingEventsRoute`；保留原evt_ID/重放/B1撤销 |
| Tracking live EventSource | 仅原`/api/v1/events/stream`→`/api/v1/tracking/events`精确alias patch |
| `apps/website/lib/service-gateway/**`、`instrumentation.ts` | 保留已验原cmd归属查询与单飞`relayOnce`；只接方向配置，不新建机制 |
| `apps/website/app/health/ready/route.ts` | 随本次B3升级补configured元数据；原Auth/Projects readiness判定不耦合worker存活 |
| 自有release工具/收件/源码绑定 | 增量扩展当前77/8及已验B4/C03来源，保留源hash+接线patch双证 |

禁止映射Tracking候选的全局`events/stream`、单来源`commands/[id]`覆盖网站入口；原Projects numeric流、Hunter hunter:N、全局command gateway均保留。已有readPaths已准确包含两个module SSE路径，不再次重建Auth singleton。

目前`ingest/tracking`仍501、观察outbox待核对，是owner已披露限制；不为“整链成功”伪造receipt或擅自开放新回调。Hunter→Projects→原commands outbox→Tracking inbox是一条链；Tracking推文/feed与主页显式成员操作分别验证，不把二者自动联动。

## 同批 readiness 元数据

原`service/status/business_enabled/profile`保持兼容；旧`workers_enabled`需明确表示“至少一个方向已配置”，而非实际存活/connected/来源交付。新增逐worker configured及发布策略的外采关闭说明，不能暴露token、私有URL或账号资料。具体字段及目标hash随B3精确收件记录，不能现在单独build/上线。

`websiteReady()`继续仅核Auth库和Projects私有IPC。测试配置存在但worker停止/不可用时，网站仍ready200，模块如实未连接/503；Auth/Projects故障仍503。不要为显示worker状态把HTTP探测加入网站就绪依赖。

## 冻结到达后的验收顺序

核最终core/control与P2取消修复绑定 → 精确merge/映射/patch → 只用隔离库跑实际Next+两worker/原cmd/推文feed/主页独立性/四库隔离 → 唯一heavy锁生产build与1440/390/权限/静默SSE/恢复 → 在线备份 → 新Tracking显式init与新job → 仅升级受保护v2 → 公网两角色/API/SSE及新job故障恢复 → 合成账号CLI禁用与撤销 → 实际三服务release/source/BUILD_ID和未验证项报告。

view hint只按批准的qv1格式/当前B1 actor+视图隔离，8槽/64MiB/60秒、C03两秒/整feed八秒/并发≤2不放宽。所有音频测试只mock，不夜间发声；voice归全站UI owner，后续按其独立冻结包收件，不阻塞本B3接入。

不再启用已退役的旧合成账号/口令。新合成账号用后禁用；私密文件不整文件预览，不在工具输出、控制台或报告展示口令/Cookie/token。保护真实admin会话，不绕过Access。
