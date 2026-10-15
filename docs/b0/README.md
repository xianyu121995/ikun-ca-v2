# UI 最终验收与 B0 基础设施验收

当前准入记录：用户授权继续完成并验收B0、提交Git，后端业务继续冻结，不合并或部署。**B0基础设施验收已通过并关闭；B1–B4/C0/D0均未放行。** 上一候选为29326c7，本次是独立收尾提交，不改写旧tag。

此记录补充冻结的phase2-spec-v1.0.0阶段状态；原API、ID、权限、四库归属及文件所有权继续有效。原tag、source-freeze和freeze-manifest保持历史原样，不通过改写旧hash假装规范没有变化。当前状态见current.json；本轮源码/文档hash见manifest.json（version 2），历史version 1仍可从b0-infra-candidate-v0.1.0读取。

## 四个最终提交

| 窗口 | 原Worktree最终提交 |
|---|---|
| 全站UI设计 | 486294ac3255b08fdb13a307ee15f96c571020d9 |
| 主页UI设计 | eb93ac7739e0ce9d74fa9859f838a7bca294ce3e |
| 猎手监控UI设计 | 08065d700239b20fb4c887bbd0c85321904687f8 |
| 猎手项目监控UI设计 | d90598f4bc595458ce26c5ee1c2e1618e318abc0 |

四处HEAD和clean状态均核实；foundation之后的diff均在各owner目录。全站视觉代码为a648e3de0ef82f15c469867fc3dba6143044ecf6，486294a只追加用户定稿文档。全站窗口根据用户另行授权，通过Git对象在内存打包三个原始稿，统一绑定该包的公共源码；没有合并或复制三个页面进主仓库。

原页面依赖pin并不相同：主页/Hunter为5ce45fd，Tracking为4527ba4。统一预览会将所有@ikun/ui导入解析到唯一定稿公共包，内层AppShell仅作容器，保留一个真实导航。验收结论针对这份用户确认的统一展示，不声称四个原分支已改成相同lock或主站已集成。

## 验证证据

- 公共包typecheck/build、13项组件测试、1项无脚本密码POST回归；主页16、Hunter7、Tracking10项模型测试通过。
- 独立无头浏览器重新验证三页×1440/1920/2560/390，共12组布局：单一侧栏/main、三个入口、活动项、无整页横向溢出。三页computed字体/标题/搜索/评分样式一致，搜索空态/恢复和前进后退通过。
- 3255运行资源与固定源码重新构建的JS/CSS字节hash相同；19个页面输入逐一与Git对象核对。请求没有业务API、外部资源或写入，CSP禁止连接。摘要见ui-acceptance.json；截图只在var/b0/ui。
- 当前26项基础设施/回归测试通过（上一候选16项）：四库边界、只读、显式初始化、四列兼容、实际冻结Tracking升级、受支持版本、私有IPC身份/超时/故障、进程树退出及父进程SIGKILL回收。
- 主仓库build/typecheck通过；基础骨架smoke与B0三服务/私有IPC合成烟测通过。测试只使用随机loopback端口和临时库。
- 公共UI在一次性干净文件系统中离线frozen install，六包串行构建、UI类型/测试通过。新增的临时Next页面实际导入公共组件和CSS并静态渲染；测试路由未提交主站。安装禁用scripts；没有运行任何实际业务服务。
- 本轮串行结果见closeout.json；源码hash与最终提交manifest一致。UI源码与四个冻结SHA未变，浏览器/UI模型证据承接ui-acceptance，不伪称本轮重新执行UI设计验收。

最初无脚本HTTP测试被sandbox拒绝listen；使用获授权的隔离loopback复验通过。验收脚本初次因esbuild初始化cwd和空态文案匹配失败，已校正并完整复验；没有为此修改UI定稿。

## B0 验收交付

1. config/b0/receiving-plan.json完成正式收件审阅且执行关闭，workspace配置与pnpm-ui-lock.yaml登记固定UI提交、website依赖及串行构建顺序。根pnpm-lock、根package和实际UI分支没有改动；清洁安装在临时目录完成，不能把候选lock当成已在主站启用。
2. Foundation迁移INSERT使用显式列，保留本轮v2候选的checksum扩展；新增独立_migration_checksums基础校验和与失败回滚，显式初始化可增补本轮v2基础库的旧元数据，HTTP只读检查不会增补。没有读取、复用旧版网站数据库。超出调用方明确声明的支持版本拒绝；基础默认只支持版本1，受控兼容验收明确支持2，不默许任意未来版本。业务迁移编号、checksum与writer仍由对应冻结owner后续负责。
3. inspectStores只读且不创建/迁移/改权限；网站启动显式bootstrap，HTTP readiness不再写库。启用IPC时Next只检查auth元数据，通过IPC检查Projects，不直接初始化或访问projects.db。
4. ManagedProjectsIpc提供短socket目录0700/文件0600、随机方向token、入口SHA256与build SHA绑定、受限子进程env、超时和故障关闭。启动前再次校验入口并复制/冻结调用参数；阻止构造后漂移，但不替代生产不可变release要求。配置缺省不启用；本轮只连接合成health夹具，真实Python Projects封装仍属于B2。
5. 三个服务启动入口各管理自己的进程树；私有guardian处理SIGTERM/SIGINT及父进程异常死亡，不使用旧版supervisor/Watch。Unix IPC基础使用[Node24 HTTP](https://nodejs.org/docs/latest-v24.x/api/http.html)；进程组行为参考[Node24官方文档](https://nodejs.org/download/release/latest-v24.x/docs/api/all.html#child_process_optionsdetached)，在本机用合成进程实测。

## 复现

在主仓库根目录，使用已固定Node24工具链：

```sh
export PATH="$PWD/.tools/node/bin:$PATH"
pnpm build
pnpm typecheck
pnpm test
pnpm smoke
node scripts/smoke-b0.mjs
node scripts/verify-ui-workspace.mjs
node scripts/check-b0.mjs
# 收尾全套串行复验（仅临时数据和loopback）
node scripts/accept-b0.mjs
```

浏览器复核命令为node scripts/audit-ui-final.mjs --playwright ABS_INSTALLED_PLAYWRIGHT/index.mjs --browser ABS_HEADLESS_CHROMIUM，默认只读取既有3255静态预览；不重启用户预览或生产进程。IPC配置结构见ProjectsAdapterConfig；B2之前不要给真实业务配置IKUN_PROJECTS_ADAPTER_CONFIG。

## 后续门槛

UI设计冻结，已有业务候选保留，不开展第二套实现。RECEIVING.md/config/b0/receiving-plan.json已完成收件方案审阅；ADAPTER-GAPS的各项已明确归入B1/B2/B3/B4/C0，没有静默修改业务协议。B0范围内无剩余阻断。未执行的正式源码收件、真实业务和生产验证是后续阶段门槛，详见BLOCKERS.md；登录系统开工条件和验收条件分别见AUTH-RELEASE.md。B0通过不自动放行认证。

后端原SHA未变；Hunter另有未跟踪services/hunter-worker/ui/，本轮只记录、未暂存/删除/覆盖，其来源不纳入B0验收。主目录原有未跟踪auth/Tracking候选与旧审计同样保持原状。
