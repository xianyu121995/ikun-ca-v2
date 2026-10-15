# 第二阶段窗口交接

当前版本 **phase2-v1.0.0**。先读 [冻结规范](phase2/README.md)、[API](phase2/API.md)、[目录](phase2/OWNERSHIP.md)、[放行和验收](phase2/RELEASES.md)。本轮立即放行全站UI设计、主页UI设计、猎手监控UI设计、猎手项目监控UI设计；范围限独立UI，不接真实业务。后端/集成新工作held，三窗口安全冻结已完成，9个候选完整SHA见 source-freeze.json。

规范在主仓库/tag只读查看，本轮不merge/cherry-pick/rebase/push或部署。下面保留原工作目录/端口指引；与当前phase2有差异的旧通用提交/接入文字以phase2为准。

# 其他窗口的开工规范

基础工程完成提交和 Worktree 建立后，此文件作为共同入口。各窗口仅按用户在自己聊天中已授权的任务开发，不得自行实现不在分工中的模块。

## 工作目录与分支

主仓库：`/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2`，由技术总管持有。

| 窗口 | Worktree（主仓库的同级目录下） | 分支 | 独占写入范围 |
|---|---|---|---|
| 全站UI设计 | ikun-ca-v2-worktrees/website | codex/website | 全站设计与共享 UI 候选 |
| 猎手 | ikun-ca-v2-worktrees/hunter-worker | codex/hunter-worker | services/hunter-worker、schemas/hunter |
| 跟踪 | ikun-ca-v2-worktrees/tracking-worker | codex/tracking-worker | services/tracking-worker、schemas/tracking |
| 再做项目管理 | ikun-ca-v2-worktrees/projects | codex/projects | 项目业务候选，modules/projects、schemas/projects |
| 登录系统 | ikun-ca-v2-worktrees/auth | codex/auth | 认证业务候选，modules/auth、schemas/auth |
| 主页UI设计 | ikun-ca-v2-worktrees/homepage-ui | codex/homepage-ui | 项目页面 UI 候选 |
| 猎手监控UI设计 | ikun-ca-v2-worktrees/hunter-ui | codex/hunter-ui | 猎手页面 UI 候选 |
| 猎手项目监控UI设计 | ikun-ca-v2-worktrees/tracking-ui | codex/tracking-ui | 跟踪页面 UI 候选 |
| 集成验收 | ikun-ca-v2-worktrees/integration | codex/integration | 集成工具与验收，不替代领域业务 |

具体提交基线与验证结果见 docs/VALIDATION.md；用 `git log -1` 核对基础提交。这里只提供规范，不触发其他聊天业务开发。

## 每个窗口先执行

在自己的 Worktree 根目录；Node 路径指向主仓库中的只读工具链。生产不能依赖开发目录工具链。

```sh
git rev-parse --show-toplevel
git branch --show-current
export PATH="/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin:$PATH"
pnpm install --frozen-lockfile
pnpm build:shared
```

每个 Worktree 已有忽略的 `.env.local` 和自己的端口配置；不得把 secrets 发到聊天。依赖/node_modules、DB 与运行数据均保持本 Worktree 独立，禁止 symlink 其他窗口 node_modules 或 var。

| Worktree | WEBSITE_PORT | HUNTER_PORT | TRACKING_PORT | DATA_ROOT（本 Worktree 内） |
|---|---|---|---|---|
| 主目录 | 3100 | 3111 | 3112 | ./var/dev |
| website | 3200 | 3211 | 3212 | ./var/dev |
| hunter-worker | 3300 | 3311 | 3312 | ./var/dev |
| tracking-worker | 3400 | 3411 | 3412 | ./var/dev |
| projects | 3500 | 3511 | 3512 | ./var/dev |
| auth | 3600 | 3611 | 3612 | ./var/dev |
| homepage-ui | 3700 | 3711 | 3712 | ./var/dev |
| hunter-ui | 3800 | 3811 | 3812 | ./var/dev |
| tracking-ui | 3900 | 3911 | 3912 | ./var/dev |
| integration | 4000 | 4011 | 4012 | ./var/dev |

窗口默认只启动自己的 `pnpm dev:website`、`pnpm dev:hunter` 或 `pnpm dev:tracking`。如需端到端测试，同一 Worktree 的三服务可以在其完整端口组启动，不连接其他窗口的数据。smoke 使用临时目录与临时端口。

## 必读与不可越界

读取根 AGENTS.md、ARCHITECTURE/API/OWNERSHIP/GIT/DEPLOYMENT。总管维护共享 contracts、runtime、根依赖和锁文件。需要新依赖/API/schema/权限时提交规范候选；不能为赶进度自行改共享文件。项目主数据与认证业务分别由“再做项目管理”和“登录系统”窗口负责，不由 UI 窗口顺手补齐。

所有外部采集和 Watch 接入在基础阶段关闭。旧版代码/库、已有监控、共享 Watch、Cloudflare Tunnel 不得修改。猎手数据只传递脱敏聚合；没有真实心跳不得声称 connected。`ready` 是存储检查。

## 提交与验收

此轮只有四个UI窗口可以新增各自展示工作；后端候选继续冻结。获放行的窗口在自己分支提交：结果、路径、SHA、契约影响、运行命令、测试证据、未验证项。不要合并他人分支、直推 main、自行部署。本轮只收件/审阅，不执行合并；后续集成须另行明确授权。

共享基础改动后需重建 shared，只有 `tsx watch` worker 自身文件变化会自动重启。正式生产必须运行 compiled `dist` 和 `next start`，不能用 watch/dev。

## 并行候选的保留

基础提交仅包含总管架构文件。其他窗口已经写入主目录的 `homepage/`、`auth/`、`services/tracking-worker/python/` 等候选和仓库外 UI/集成目录保持原状，不属于基础提交，不删除、不覆盖、不宣称已集成。9个窗口现已在原Worktree冻结，不再从主目录重复复制/开发；不得从主目录整体git add。现有Python候选的三服务封装已由phase2/STORAGE.md规定，后续按放行批次适配，不擅自增加正式服务或绕开认证。

权限必须只有 superadmin/user；所有业务写入仅 superadmin，user 只读，不开放公开注册。基础 Auth route 关闭状态不是已有认证候选的验收结论。
