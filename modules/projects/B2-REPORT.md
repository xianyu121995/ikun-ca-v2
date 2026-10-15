# B2 本地交付记录

> 历史首版：`f89c58e639ca9d844ebead5d019c29f0476d5314`。总管退回三项修订，本文件的155项及哈希记录保留为首版证据；当前修订结果见 [B2-REV1-REPORT.md](B2-REV1-REPORT.md)。以下“本地通过”不表示总管验收通过。

本地功能与隔离验收通过：155 项 pytest（原71项 + 新84项），其中一项执行9项真实 B1/Next 入口 Node 子测试，不重复累加。B2 总体验收仍 pending；正式网站收件、真实 worker 联调、公网与生产未验收、未部署。最终完整 Git SHA 在交付消息和忽略的 `artifacts/final-receipt.json`，本报告随该提交保存。

## 来源与范围

原 Worktree `/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/projects`，分支 codex/projects，基线 `7f8a4610b4dcdda1f0785c2fc3c73a18ebdeb35f`。仅修改 modules/projects/**、schemas/projects/**；没有改写历史、合并、推送或收件其他 owner。

有效 profile：phase2-v1.0.0 + auth-b1-final-v2 + projects-home-v1。

| 来源 | 固定完整 SHA |
| --- | --- |
| B2 正式放行 | 4b2e33b0d4996c93d6df9bd5ef265fe0d2ddcaf5 |
| 主页增量批准 | 6595c4a05b736889a4649b1d0aa7405601deebc4 |
| 集合增量批准 | 379c6e583e487f038629e1ca24d4b2614970ad0c |
| phase2 规范 | 9699375c920465b5d802e7acff17b5421203e544 |
| B0 | 85be3bd6dce25d82033b6cb1a7157aaa39bd571e |
| B1 审核 | c0f86bc20fc7b3ca147da863759b98acced8de44 |
| Auth 源码 | 28e6aaf4141790fc74ae4ae4429be4b854460955 |
| 公共 UI | 486294ac3255b08fdb13a307ee15f96c571020d9 |
| 定稿主页 | eb93ac7739e0ce9d74fa9859f838a7bca294ce3e |

## 实现

沿用原 CRUD/来源解析/审计，新增正式 DTO、严格迁移、查询和私有 IPC 适配。评分 S/A/B/C/D/null、简介/官网/备注/分类/阶段/百分比/日期可持久保存。ProjectRecordV2 不增加隐式字段，home-v1 明确投影 project/milestone/completion。

独立事件保存日期、00–23或未知小时、标题与状态，固定北京时间，不借用 token_date。主表和弹窗在 SQL 分页前完成集合、过滤、排序及真实 total；未知值排序末尾、ID稳定打破同值；独立 summary 和事件不继承主表页/q。cursor 绑定 scope/profile/完整查询/集合/limit。

完成操作保留修改前真实阶段与百分比；批量全成或全回滚。重复完成不覆盖快照/时间或增 revision；恢复沿用 ID 和真实快照，保留历史。新建即完成标注 creation_default，恢复 researching/null。旧 completed 无快照拒绝猜测。普通 remove/add 只改成员状态，不控制其他模块。

写入有 UUID 幂等回执、If-Match/ETag、角色与错误处理。unknown 查询当前 actor/scope/method/path/contract 的原回执；404继续 unknown，不盲目重发。受控 Hunter confirmed 事件在同一个项目库事务内写 canonical、inbox 和沿用 command_id 的 Tracking outbox。来源引用或官网冲突409，不覆盖人工资料；重复/并发/handle变化复用稳定平台映射。Tracking 投递仅提供单次网站 owner 函数，丢失 ACK 先 GET 原 command；没有自动采集或真实 worker 调用。

正式 Python 入口只开 DATA_ROOT/projects/projects.db，不读取 Auth/Hunter/Tracking。B0 管理 UDS 子进程，0600 socket/0700目录、随机方向凭据、build_sha与入口hash；没有正式8120服务。Node 只使用 B1 Auth 与 IPC，不打开项目库。角色在实际 handler/page/action 检查，Proxy 使用同一审核白名单。SSE逐块和静默期验证撤销。

已显式创建空白独立库：`modules/projects/data/b2/projects/projects.db`（忽略入Git），业务版本2、项目数0；没有导入演示或生产数据。没有初始化持久 Auth 账号；本次 Auth 写入只来自已验收 B1 组件的临时合成测试。

## 测试与证据

| 测试文件 | 实际计数 | 覆盖 |
| --- | ---: | --- |
| test_projects.py | 63 | 原 CRUD/版本/身份候选/来源/租户/分页/路径/异常保障，保留历史回归 |
| test_browser.py | 8 | 原独立候选页面回归，不能代替新版 B1 验收 |
| test_b2_domain.py | 54 | 正式迁移/旧ledger/rollback/checksum/未来版本/权限/幂等/游标/并发导入/跨库边界/IPC错误 |
| test_b2_home.py | 18 | 00/23/null、原子事件、完成周期/并发/批量回滚/创建默认、113条分页、集合完备性、计数/事件独立、回执作用域 |
| test_b2_browser.py | 9 | 真实 Next/B1/私有IPC、1440/390 CRUD/刷新持久化/页选择/独立弹窗分页、首次改密与user只读、乱序响应、丢失回执、实际网站TERM/KILL/IPC故障 |
| test_b2_lifecycle.py | 3 | 实际 B0 IPC 子进程正常退出/子进程强杀/父进程强杀、路径/凭据更换与持久化重启 |
| **pytest 合计** | **155** | **0失败、0错误** |

Node 子测试通过真实导出的 handler、B1 请求上下文中的 page guard/Server Action 执行；无 Proxy 仍拒绝匿名、伪造角色、CSRF/Origin/Host、scope、强制改密与过期。测试退出、禁用、本机重置、本人改密轮换和七天过期的 API/SSE 撤销；本机 Tracking HTTP 夹具丢失 POST ACK 后仅 GET 原ID，未第二次POST；入口 hash 漂移和子进程启动失败受限回收。

原基线替换映射：独立 Bearer/本库 session 的旧测试仅保留兼容回归，新正式身份由上述 B1 入口/SSE测试覆盖；offset 旧接口保留，新正式列表用 query-bound cursor；旧页面由新版定稿 server 模式真实浏览器补齐，不把原71分数冒充新版通过。

实际命令：

```sh
B2_NODE=/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node python3 modules/projects/integration/build-preview.py
cd modules/projects/candidate
.venv/bin/python -m pytest -q tests --basetemp=/private/tmp/ikun-b2-full-regression --junitxml=../artifacts/pytest.xml
```

Node24.22.0、Next16.4.1完整生产模式串行构建通过；contracts/runtime/UI/Auth在Next之前完成。构建源集合 SHA256：`e227926ddf3af6ae575ffaab92dcdde5a52d5b1e9880782aa4775ac0644a11b1`。48个本模块代码/测试/SQL输入哈希见 [build-inputs.json](integration/evidence/review-f89c58e/build-inputs.json)；另核对26个 B0/Auth/UI 原始源码文件与固定 Git 对象字节相同，见 [frozen-inputs.json](integration/evidence/frozen-inputs.json)。测试源码与构建源码未漂移，最终提交后再以实际提交 SHA 执行新版接线回归并写 final-receipt。

UI 补丁 SHA256：`d008da704e87f48d9c39f2db9c33eacb97bbf5fa8370f6444e77453902bf59f3`。仅两个UI文件的 server 模式输入/回调/分页接线，补丁留在 Projects 自有目录；原定稿不变，没有改CSS/文案/导航。截图：[1440](integration/evidence/review-f89c58e/homepage-1440.png)、[390](integration/evidence/review-f89c58e/homepage-390.png)。图片使用合成数据，无真实账号/项目信息；横向表格在自身容器滚动，文档无横向溢出。计数/截图哈希见 [test-receipt.json](integration/evidence/review-f89c58e/test-receipt.json)。

早期失败记录保留在隔离 /private/tmp/ikun-b2-* 测试目录，没有改写为成功：修正测试选择器；修复空 DELETE 流误报、异步集合旧 revision 覆盖与弹窗翻页竞态；修复 Uvicorn 0.54 SIGTERM 重放跳过 socket 清理。最终以上完整回归通过。唯一警告为 Starlette 对 httpx TestClient 的弃用提示，不升级既有锁定依赖。

## 总管待收件与限制

- 收件候选：网站真实路由/page/action/proxy、B1精确只读白名单、`lib/stores.ts` 的精确 Auth2 + IPC readiness、B0托管启动候选、公开 UI 依赖/锁和两文件 UI 补丁；全部只保存在 integration/或忽略预览，未写正式归属路径。
- **BLOCKED：正式网站/公网/真实 Hunter 与 Tracking 集成验收。** 原因是相应 owner/阶段仍冻结且尚未正式收件；本地协议夹具不是运行或connected证据。
- **未执行：带活跃旧候选身份的业务库升级。** 迁移器显式拒绝并保留原库，需 owner 审查身份退役；空身份旧库、旧 foundation、已有业务库重复迁移/重启已测试，不伪造无损身份迁移。
- B0 父进程 SIGKILL 可留下空0700临时目录；实际子进程/socket/网站监听器已验证退出，测试按自身记录回收空目录。不会复用遗留 socket。不可直接把忽略预览当生产不可变发布目录。
- 没有重启旧服务、触碰生产数据库、Watch、Tunnel、真实平台或付费接口。没有 merge/cherry-pick/rebase/reset/amend/push/deploy。

运行步骤见 [integration/README.md](integration/README.md)。本地通过不等于主站 READY，B2 总体验收仍 pending。
