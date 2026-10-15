# B3 受保护 v2 上线验收

B3 Tracking 已接入 [v2.ikun.ca/tracking](https://v2.ikun.ca/tracking)，本地生产验收、独立作业恢复及公网权限验收通过。范围是受保护测试站、外采关闭和明确的本地合成数据；真实来源与正式 ikun.ca 上线仍未批准。

## 实际版本与接收

网站及新 Tracking release：`64088893841122491aba508fdb514507db3d9339`；生产 BUILD_ID：`QTLRQ2vGatyCJCEhtFEVA`。同一网站运行字节完成本地76项和公网验证。构建之后仅接收部署预检增量及运维证据，网站源码/compiled 未改变，没有把报告提交误写成运行版本。

B3 原源码 `c4de379a67bd9b154bab87ce81d4645b53102ea0`，交付 `f3bc19503ae33e000bdd33c140baa1fe77c9109a`，冻结控制 `d0af2804ed1ad70d3dd66e930582831bbd6b5e96`。独立 venv 预检增量 `f67ba31dd034b3cd590ec7740c998b111d337ffa`，批准 `f2f492dec3266e3204cffce1ede571f36d04bd5f`；原62个源码哈希仍逐一核对，只给 preflight 一个精确运行文件例外，另列获审测试/交接文件。

Hunter 继续运行原 release `75b81a2b5210e41bdf8522467c7fba2a6a6e693c`、原业务源码 `10fe9d73dcf9d2dd296b808e8aaee41308f12112`。原 job/plan/env/plist 字节及 PID 2608 保持不变；不是重新部署 Hunter。Auth/Projects 原数据、管理员账号和会话保留。

接线严格按 NIGHT-SOURCE-MANIFEST：36个网站/UI文件，冻结 UI 补丁2个输出，额外3个精确接收 patch（Tracking URL alias及两个入口的既有 B1 初始化）。保留 Projects 全局流和已审严格 command gateway，不收 owner 的 preview 全局流或 commands route。原77来源、8主页和247个 B4/C03 域路径检查保留；实际 release 核验311源码、248编译文件。

## 本地生产验收

76项断言在真实生产 Next、compiled Hunter、compiled Tracking、四个新隔离库上通过。此前74项通过不累计；之后只补反向移除隔离，复跑同一构建76项。两角色1440/390的 Hunter/Tracking共8张截图，Tracking最终四张人工视觉核验。

覆盖发现、人工确认、原 command 幂等、Hunter 受控 loopback→Projects 私有IPC→已有 outbox→Tracking 订阅、严格 gateway 原ID回查、权威 Projects 评分→C03 UDS→published feed、显式加入主页、双方移除不连带、四库不同 inode/integrity/FK、普通用户写入拒绝、Tracking 停启不影响网站/Hunter/网站 ready、禁用后 API401 与静默 SSE 撤销。

推文在该隔离 Tracking 停止后，经冻结 normalizer/Store 离线插入并验证去重，再重启展示；没有并行第二个 writer、fixture HTTP入口或真实来源调用。这证明本地接收存储后的投影与展示，不能冒充实际 WSS 收包。真实来源关闭时订阅没有被标成远端 running/connected。

分列测试：严格 gateway12通过；守卫原38项通过；预检由总管独立复验同套36通过；owner131核心及其嵌套 Node/历史浏览器不在这里重跑或累计。首次 gateway 命令缺 `--import tsx` 导致模块解析失败，使用项目现有 loader 后原12项通过，未改业务实现。第一次无Cookie探测按历史302作断言失败，实际结果403保留，见公网说明。

## 实际作业、数据库、备份与回滚

三个业务 job 为 `ca.ikun.v2.c0lite.web` / 4000、原 Hunter / 4011、新 `ca.ikun.v2.c0lite.tracking` / 4012；现有 Tunnel 只是入口。网站继续托管既有私有 Projects IPC，不新增业务服务。

新 Tracking 使用私有 job cwd、绝对 release entry.py、独立 `ROOT/venvs/tracking`、600配置和方向 token 环境变量。启动前显式 init/migrate，再从实际 release 使用 `-I -B --venv-root` 预检：prefix、无目录别名/越界/隐式.env、entry/锁哈希、25个安装版本、本库身份、外采关闭均通过，之后才安装 job。守卫固定 Python venv 路径，校验 Node 可执行文件哈希；不声称额外校验了 Python 二进制哈希。

launchd 强杀新 Tracking 后恢复至 PID25225，网站25136与 Hunter2608均不变。四库均600、单链接、不同物理 inode、integrity/FK通过：Auth v2/app-id1229652484，Projects v2/1229652483，Hunter v4/1229652481，Tracking v4/1229652482。没有覆盖旧库或将库互相链接。

网站 ready 仍只检查 Auth+Projects IPC；workers字段现在表达已配置，不查询或依赖独立 Worker 存活。外采状态从 Worker 自己的 ready/status确认关闭。Next生产模式和既有768MB heap保持，Tracking启动守卫使用256MB Node上限、独立Python固定依赖、限并发/超时沿用冻结实现。

升级前3库、升级后4库均执行 SQLite 在线 backup并校验。独立日志600，内部扫描三个方向凭据值未出现在服务日志。自有网站/IPC/双Worker/Tunnel RSS最后快照204.6MiB，不是8GB压力或长期稳定性结论。

网站升级分 stage 与启用：先归档新 release并核对全部源/编译哈希，原服务不动；迁移/预检成功后才启用。启用失败自动恢复原 web plist/env/owner。原 release、升级前私有配置及部署回执留在 `ROOT/rollbacks`，备份在 `ROOT/backups`，具体路径见私有 deployment 报告。Tracking可按已验精确 plan unload 仅撤下新作业并保留库；未执行真实回退、降schema或恢复覆盖测试站业务库。

## 公网与安全收尾

原正常Chrome管理员经既有Access进入新Tracking页，auth200/superadmin，Projects200且原主页1条、Hunter200且原发现1条、Tracking订阅/评分feed200且0条。新Tracking空库保持空库，没有为了公网画面写fixture或伪造运行/推文。标题与导航“猎手项目追踪”正确，未连接真实来源/合成测试说明可见。

一次性普通账号经Access后的独立无痕会话登录：主页显示只读，Tracking账号抽屉显示“只读视图”；三个域读取200，Tracking POST/PATCH/DELETE均403。首账号禁用后页面自动跳登录，清掉控制台，未把该次当作正常EOF证据。另建新一次性账号在静态同源页验证：SSE200，禁用后 normal EOF；随后 Auth/Projects/Hunter/Tracking四个API均401。该流总共数到1个event帧，未采帧类型，不写成0帧；窗口内没有业务写，实际Tracking changes表仍0行，冻结API会发heartbeat。

两个新测试账号均CLI禁用、会话撤销、口令字段删除；未复用B4已退役账号或口令。临时随机口令仅600配置指定字段进入密码输入，不预览文件、不输出内容；内存变量清空。真实管理员口令未读取，管理员随后仍auth200/superadmin，原主页/发现记录保持200各1条。

无Cookie HTTPS四入口实际返回 Cloudflare403（证书验证通过），没有把它改写为302或直接当作Access产品层证据。全新Chrome访客最终到Cloudflare Dashboard登录页，显示Sign in to Cloudflare、应用内容不可见；未输入任何验证资料。未改已有Cloudflare、Tunnel、DNS、Access规则或主域名。

## 仍未完成的整体范围

真实6551/WSS/REST/付费/共享Watch联调仍未授权；`/internal/v1/ingest/tracking`仍501，观察outbox pending不代表送达，主页实际推文接收闭环不能宣布全部完成。语音已由UI另行冻结，接入安排在本次B3公网记录归档之后；未真实发声。独立OS用户、长时间驻留/压力及日志轮转观察、正式域名切换仍未验收。main保持`63e8a2857241c6a76226f21435e40db9736a1e7e`，旧版服务/库/共享配置不变。

机器可读结果与私有证据哈希：[b3-acceptance.json](./b3-acceptance.json)。私有证据在`release-integration/.runtime/night-b3`：deployment、final-runtime-audit、public-verification及各脱敏角色/禁用/SSE/访客结果。报告仅声明受保护测试站B3通过。
