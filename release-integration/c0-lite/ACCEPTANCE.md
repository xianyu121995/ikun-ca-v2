# C0-lite 集成验收记录

本地结论：Auth + Projects 实际 Next.js 生产入口通过，公网受保护测试站尚待云认证与实际 Access 验证。完整新版发布仍为 BLOCKED，不能把本报告解释为正式 ikun.ca 上线验收。

## 授权与候选

- 授权控制提交：`c30cc51f64e95c40a6ccd83b1fbed458090ef3be`，`codex/c0-lite-control`。
- 集成分支：`codex/integration`，从冻结点 `c4845f54feb15623b20720ce83340f61c110b372` 向前合并，未 rebase/reset/amend。
- 依次合入 B0 `85be3bd6dce25d82033b6cb1a7157aaa39bd571e`、UI `486294ac3255b08fdb13a307ee15f96c571020d9`、Auth `28e6aaf4141790fc74ae4ae4429be4b854460955`、主页 `eb93ac7739e0ce9d74fa9859f838a7bca294ce3e`、Projects `d0fdefab2aa230ebb8df856aed306d0184d362e2`，均无冲突。
- 合并完成点 `c79df194d536dc479f8228c41bad5644eff75024`。首轮 80 断言在此点加接线工作区执行；追加文字修正的 82 断言在 `60afd9cafa4ab3a558021a758871eba9a7aca17b` 加文字修正工作区执行。最终提交包含绑定的源文件字节，不能把测试时 HEAD 伪称为最终提交。
- `evidence/build-binding.json` 固定 186 个实际输入文件与 220 个编译输出 SHA256、lock SHA 和 BUILD_ID。部署脚本逐项检查，最终 Git SHA 写入新运行目录、IPC identity 和部署回执。
- 77 个领域/共享源文件和 8 个主页文件均与批准哈希一致。25 个入口映射、21 个根级允许文件及两个鉴权占位页的范围受外部控制检查器约束。
- `main` 保持 `63e8a2857241c6a76226f21435e40db9736a1e7e`，未 push；未改旧版、Watch、原 Tunnel、apex/www DNS。

## 实际入口与数据

正式 `apps/website` 收入已验收 B1/B2 入口，使用 B2 Proxy/stores 与独立 Auth 库；首页收到真实项目服务查询和写命令、回执、SSE。UI 只应用批准补丁，原型入口返回 404。本人追加要求的“猎手项目追踪”由接收层使用共享 UI 的 LinkComponent 扩展点纠正可见文字、title 与 aria-label，冻结共享 UI 与主页文件未变；两个屏宽均已验证。

实际 `next start` 启动 B0 管理的独立 Projects IPC 适配器，显式新路径与显式迁移，无自动迁移，无 provider 访问。`/hunter`、`/tracking` 需先登录并明确显示“未接入”，未合入或启动 B3/B4。这里的 Projects IPC 是项目数据适配器，不是项目监控引擎。

## 已完成验证

| 验证层 | 结果与证据 |
|---|---|
| 锁定依赖安装、生产构建、类型检查 | 全部命令退出 0；Next 16.4.1、Node 24.22.0、pnpm 10.33.1，BUILD_ID `LA6FmUJ_Kd5JYYimMFVkO` |
| B1 原始回归 | 54/54；实际接收根目录的 B0 编译运行时，非 preview 副本 |
| B0/基础回归 | 26/26；仅测试进程恢复 umask 022，使不安全权限样本确实为 0644，运行服务仍为 077 |
| 实际入口守卫 | 9/9；`evidence/entries-1792076678170.json` 与同名 TAP |
| 实际生产构建 P0 | 82 断言通过；`evidence/p0-1792078622372/result.json` |
| 浏览器 | 1440/390 登录、首次改密、会话旋转、只读权限、游标翻页、增改/刷新/完成/恢复、独立重要事件；脱敏截图同目录 |
| 备份恢复 | 在线 SQLite backup 到新路径，Auth/Projects integrity、外键、逻辑内容相等；未覆盖源库 |

AUTH-01/02：匿名页面和 API 拒绝，普通用户所有写方法拒绝，伪造身份/跨 scope/缺失 CSRF/跨 Origin 拒绝；无网页账户管理。无 JS 登录/改密表单采用 POST，不能把密码放进 URL。

AUTH-03：真实 TTY CLI disable/reset/recover、网页 logout/本人改密；旧 API 和静默 SSE 会话撤销，始终仅一个有效超管。PRO-01：真实幂等写入、revision 冲突、持久化、丢弃成功响应后查原回执（不再次 POST）、超过 100 条的数据库游标与服务端过滤。PRO-02：独立里程碑、完成保存实际 37% 快照、恢复原进度、移出监控不等于完成。ISO-01：Auth/Projects 相互操作不改对方数据，Projects 无账户/会话表；H/T 合成引用不变仅属隔离样本，不能代替真实监控跨库验收。

## 保留的失败记录

- 首次构建成功后，B1 一项测试因接收根目录没有 preview 路径描述失败；新增描述指向实际已构建根目录，未复制 preview，54 项随后通过。
- B0 权限拒绝测试最初 25/26：外层共享重任务锁 umask 077 把测试拟创建的 0644 降为 0600。仅通过测试 preload 纠正样本权限后 26/26。
- P0 的早期尝试分别为测试 DELETE 缺少 Content-Type、异步按钮立即读取的竞态、测试 label 未包含 UI 的必填星号；仅修 QA 请求/等待/选择器后通过。失败 JSON 与后续通过证据全部保留。
- 汇总回归曾在受限工具沙箱中启动，UNIX socket 子进程被限制导致 21/26；同命令在授权本机隔离执行权限下重验。该失败回执保留，不属于应用改动。
- 没有重写冻结业务代码来迎合测试。

## Mac 新测试环境

`deploy_c0_lite.py --candidate <当前已提交候选 SHA>` 只接受干净集成分支和未变 main；拒绝已存在的目标目录、plist 或 label，完整复制已验收构建与内部依赖，拒绝跨 checkout 链接，Node 固定到新运行目录。使用独立生产 Python 依赖清单，不安装测试浏览器到部署环境。

新根目录固定 `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite`；新 label 固定 `ca.ikun.v2.c0lite.web`。只绑定空闲的 `127.0.0.1` 端口，`NODE_ENV=production`、Next 单 CPU 构建、Node heap 768MB、Nice 5、launchd KeepAlive/30 秒节流。heap 是每个 Node 进程限制，不是全部服务总内存上限。HTTPS origin 固定 `https://v2.ikun.ca`，无开发 Cookie 例外。新 Auth 空库等待本人 TTY bootstrap；不预设正式密码、不复用合成超管。

运行回执位于忽略目录 `release-integration/.runtime/c0-lite/deployment.json`，部署后再执行 `verify_c0_deployment.py`，记录精确新 job 的 SIGKILL/KeepAlive 恢复、进程 RSS、新库在线备份结果。代码候选与运行回执分开保存，避免为记录部署结果改变已运行代码 SHA。

## 未完成的门槛

1. Cloudflare 本机官方授权已完成，已创建新 v2 Access 应用（全路径、唯一精确本人邮箱 Allow、HttpOnly/绑定 Cookie）及新独立 Tunnel，未改现有两个应用、原 Tunnel 或原三条 DNS。最终发布状态查看忽略目录的 `cloud-publication.json`；真实已授权浏览器的公网应用登录、SSE 和拒绝验证仍需本人会话与应用初始账户。遇到登录验证停下，不放宽策略。
2. 猎手发现→人工加入监控→真实推文→主页展示，以及 hunter/tracking/projects 实际三库互删与独立监控进程恢复，本阶段未接入，不能声称已完成。
3. C-01 至 C-05 产品冲突仍保留，未自行裁决或变更语义。
4. 此测试站备份为手动验收生成；无人值守日志轮换/定时备份、完整三引擎资源上限和机器重启登录后的恢复仍需后续运维门槛；LaunchAgent 要求本用户登录。
5. 本阶段没有正式站切换。回滚只涉及新 label/新路由，旧服务与旧数据始终保留。

本次新环境初始本机部署提交为 `60afd9cafa4ab3a558021a758871eba9a7aca17b`；追加文字修正后新 release 使用新的接线提交，通过 `upgrade_c0_lite.py --from-sha` 只替换已确认归属的新 label，原 release/plist/environment/owner 回滚副本保留，Auth/Projects 数据路径不变。
