# 模块代码所有权

一个模块只有一个活跃窗口写入。所有窗口在各自 Worktree 中提交，主目录与共享文件由技术总管持有。窗口可以阅读契约，不能直接修改其他窗口文件或替其完成业务。

| 角色 | 可写路径 | 不可自行修改 |
|---|---|---|
| 技术总管 | 根配置、AGENTS.md、packages/*、scripts/*、tests/*、docs/*、.github/*、共享迁移基础 | 旧版任何服务/数据库/Watch |
| 网站窗口 | apps/website 的 UI、route/BFF（已分配领域） | package.json/锁文件、共享 contracts/runtime、projects/auth 业务（未单独授权） |
| 猎手窗口 | services/hunter-worker、schemas/hunter | 其他模块 DB/API、共享 Watch/账号、根依赖 |
| 跟踪窗口 | services/tracking-worker、schemas/tracking | 其他模块 DB/API、根依赖 |
| 项目领域窗口（再做项目管理） | modules/projects、schemas/projects、约定的网站项目路由 | auth、worker、contracts |
| 认证窗口（登录系统） | modules/auth、schemas/auth、约定的网站认证路由 | worker、project 主数据、contracts |

各目录 package.json 初始归总管；依赖变动先报告，避免并行修改 pnpm-lock.yaml。contract/API/schema 变更是集成变更，须同时给出消费者兼容与测试。每个 PR 一个模块，涉及共享文件另列协调项；不得以重构理由越界。

GitHub 账号/组织未提供，`.github/CODEOWNERS` 当前是注释模板，不宣称远程强制 review 已启用。私有仓库创建后由总管填真实 owner/team，启用 required code owner review、main/develop 禁止直推、CI required checks（具体能力依账号套餐）；当前以本 AGENTS 与人工集成审阅为规则。

全站UI设计、主页UI设计、猎手监控UI设计、猎手项目监控UI设计分别持有独立 Worktree，UI 候选不能直接改 service/contracts；共享 UI/API 的接入先交总管与对应领域 owner 审阅。集成验收窗口独立保存验收工具，不在主目录代写业务。
