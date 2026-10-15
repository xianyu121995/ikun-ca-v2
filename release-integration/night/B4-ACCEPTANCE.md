# B4 受保护 v2 上线验收

结论：B4 Hunter 已在 https://v2.ikun.ca/hunter 接入并通过本轮验收。仅受保护测试站及本地合成夹具；Tracking核心/作业/库未接入，真实平台未启用，不是新版全部功能或正式 ikun.ca 上线验收。

## 实际运行版本

- 网站与Hunter release：`75b81a2b5210e41bdf8522467c7fba2a6a6e693c`；最终生产BUILD_ID：`GEeQtBnxMYzLHcpnuweJS`。
- Hunter冻结源码：`10fe9d73dcf9d2dd296b808e8aaee41308f12112`，根冻结control `7a90ec281211cc8a307692c8e420cf4b802ce452`；C03依赖 `aa51a640a159e4c8f6cdd841a25f4279e73075ba`。
- 接线协议 `v2-site-gateway-v1` / `8b84ee97a94bae28e98b550b2721991f30088486`；gateway复核 `98fc94c410c4f1a806c9c7b11f914802aaad50ae`。
- 实际release核验254源码/240compiled；原77来源/8主页校验保留，247个域路径/35个接收映射及9份接线patch均有源与目标hash，9份patch逐项独立应用验证。B4原42源码/80证据/27映射与2份UI补丁输出保留，没有收preview/probe/未追踪UI。

## 本地与公网证据分开

42项实际Next+独立Hunter深链检查在BUILD_ID **`h54nVd6ExsdavQ3VJlvEa`** 完成。之后仅追加既有WorkspaceLink导入及live LinkComponent绑定两行，满足用户已确认的“猎手项目追踪”导航文案；公共组件/demo分支不改。最终 **`GEeQtBnxMYzLHcpnuweJS`** 已重新生产build/typecheck，并实际完成下列公网验证。没有把42项写成在最终BUILD_ID上重跑。

本地42项覆盖真实B1登录/首次改密、匿名拒绝、普通用户写入拒绝、原Projects流/模块原生cursor、人工确认与原cmd幂等、Hunter→loopback接收→Projects IPC→hidden canonical、显式加入主页与移除、跨库不连带、静默SSE禁用撤销、两角色1440/390浏览器。Tracking不存在时503/未接入，未制造running、推文或完整后续链。

其他测试分列：Auth68项；B0原26项中首轮21通过/5个IPC未就绪，保留失败并在允许本机socket环境仅复跑5项通过；command gateway12项（总管独立同套12，不累计）；部署守卫31项（保留原19）。本轮没有重复跑B4 owner已冻结的227项/14浏览器组或把历史/嵌套计数累加。

公网由原已通过Access的正常Chrome管理员窗口和无痕普通用户窗口实测：

- admin：auth200/superadmin、Hunter读取200/1条明确合成发现、管理能力true；导航为“猎手项目追踪”；Hunter/Projects错源cursor均422，未接入Tracking501。
- user：auth200/user、Hunter读取200、管理GET403、POST/PUT/PATCH/DELETE全403；研究表单字段和保存/加入按钮禁用，有效可操作控件0。最初用DOM disabled属性统计12不含fieldset继承，已用`:disabled`及AX核正为0，保留诊断说明。
- Hunter SSE原生`hunter:1`到达；合成账号CLI禁用后，在无新业务事件时原流关闭、API转401，页面清除原行。管理员随后仍auth200/superadmin、Projects200且原主页1行保留。
- 无Cookie的HTTPS页面/API/SSE三入口全部302至现有Access。全新Chrome访客最终到Cloudflare Dashboard登录页，应用内容不可见；没有输入验证信息，也未把该页面称为Access OTP页。未改变任何Cloudflare配置。

## 服务、数据库与资源

新label `ca.ikun.v2.c0lite.hunter` / 127.0.0.1:4011，独立私有cwd、env、venv、日志与Hunter库。网站保留原v2 label/4000及受托管Projects IPC。Hunter强杀后launchd恢复为PID 2608，网站PID保持不变；两者ready200。Tracking label未安装，不能以现有Tunnel计作第三个业务引擎。

Auth/Projects/Hunter三个当前库均为0600、单链接、不同inode，integrity/foreign-key通过；新Hunter schema4/app-id正确。新Hunter首次启动前才离线通过本owner夹具写2个虚构Hunter/1条“本地验收夹具”发现，没有fixture HTTP入口。旧数据/账号/脚本不复用、不覆盖，既有Auth/Projects数据保留；Tracking库不存在。

外采false，画面明确“未连接真实来源”；Hunter当前网络端点仅loopback。固定生产Next、website Node heap768MB，Hunter Node守卫256MB后exec独立Python，冻结依赖安装到独立venv。当前自有网站进程树/Hunter/Tunnel RSS快照合计142.2MiB，**不是8GB压力或长期运行测试**。

独立日志0600，扫描未发现两个新方向token。升级前Auth/Projects、升级后Auth/Projects/Hunter均用SQLite在线backup并核验完整性，未cp运行库/WAL。具体备份/回滚路径见私有deployment报告。Hunter失败可用精确计划unload仅卸载新job并保留DB；网站既有upgrade回滚保留上一release及原config/plist/owner，不降schema或覆写库。

## 安全收尾及剩余项

合成只读账号口令曾因私密文件预览工具意外显示。该账号已禁用、会话/API401且SSE关闭；本机password字段已删除，内存变量已清空，口令退役。真实admin口令/provider秘密未读取或输出；新v2方向token仅在私密部署/审计脚本内生成/加载，未展示或进入服务日志。未复述任何口令值，真实admin会话保留。

网站health中旧`workers_enabled:false`是C0遗留元数据，不表示Hunter未运行；已按总管指令登记下次B3计划升级补准确configured/外采元数据，网站ready不依赖worker存活。本次不为该字段单独构建/升级。

未验证/未完成：B3与Tracking真实后续链、真实6551/REST/付费/共享Watch、正式域名切换、独立OS用户隔离、8GB压力及长期日志轮转/驻留观察。未改main、ikun.ca主域名、已有Cloudflare、旧版服务或共享Watch。

私有证据：

- [公网断言](/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/night-b4/public-verification.json)
- [运行审计](/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/night-b4/final-runtime-audit.json)
- [部署/备份/恢复](/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/night-b4/deployment.json)
- [本地42项](/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/night-b4/site-acceptance-1792089730044431000.json)
- [临时账号安全收尾](/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/night-b4/public-temp-cycle.json)
