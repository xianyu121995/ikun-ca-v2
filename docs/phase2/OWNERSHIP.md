# 第二阶段目录和文件所有权

机器清单为 `ownership.json`。前缀匹配目录，files精确匹配文件；未分配路径必须先报总管。目录所有权不代表阶段已放行，必须同时满足 releases.json。

| 窗口 | 唯一可写范围 | 当前授权 |
|---|---|---|
| 全站UI设计 | packages/ui/**（公共组件、样式、文档、包内测试） | UI0；package.json仅现有冻结依赖/导出，不新增root依赖 |
| 主页UI设计 | apps/website/components/homepage-ui/**、features/homepage/**、app/prototypes/homepage/** | UI0；不改rootpage/API |
| 猎手监控UI设计 | apps/website/prototypes/hunter-discovery/**、features/hunter-discovery/**、app/prototypes/hunter/** | UI0；不改worker或正式/hunter接线 |
| 猎手项目监控UI设计 | apps/website/features/tracking-prototype/**、features/tracking/**、public/tracking-prototype/**、app/tracking/** | UI0；仅展示/演示候选，不接业务API |
| 登录系统 | modules/auth/**、schemas/auth/**；后续放行的api/v1/auth、login、auth路由 | 已冻结；B1前不新增后端修改 |
| 再做项目管理 | modules/projects/**、schemas/projects/**；后续放行的api/v1/projects、internal/v1/ingest/receipts、api/v1/commands | 已冻结；B2前不新增后端修改 |
| 猎手项目监控跟踪 | services/tracking-worker/**、schemas/tracking/**；后续api/v1/tracking | 已冻结；B3前不新增后端修改 |
| 猎手监控 | services/hunter-worker/**、schemas/hunter/**；后续api/v1/hunter | 已冻结；B4前不新增后端修改 |
| 集成验收 | release-integration/** 的自己的工具、文档、验收候选 | 已冻结；C0前不新增集成工作，不执行合并 |
| 项目总管 | 根配置、docs/config/scripts/tests、contracts/runtime、root网站配置与全站入口 | 此轮仅规范、类型与校验，不代写业务 |

保留给总管：根 package.json/pnpm-lock/pnpm-workspace/tsconfig、AGENTS、网站 package/tsconfig/next.config/next-env、app/layout.tsx/globals.css/page.tsx、proxy.ts、lib/stores.ts；及health、通用catch-all、/hunter正式入口、SSE与共用service gateway。页面owner不得另建网站级AGENTS来覆盖其他窗口规范。

各模块的最终路由接线先留在自己模块integration候选，由总管在获授权的集成阶段安排；不能把拥有业务API子目录理解为可直接替换全站proxy。其他窗口只读公共组件接口，不复制其实现、不改它的源码或依赖。

schemas归属按物理库，不以相同迁移编号互相影响；同一个库的编号、checksum与writer变更需总管审阅。全站UI owns packages/ui，总管只owns packages/contracts/runtime，不再用模糊的 packages/* 规则造成冲突。

所有窗口保持原Worktree和分支，保留已冻结代码。新改动另提交，不能reset/amend冻结提交、删除残留、强制覆盖/推送、合并他人工作或自行部署。Git hook必须正常执行；白名单暂存，不git add整个主目录，不提交DB/秘密/venv/运行数据。

GitHub owner/team尚未确定，CODEOWNERS仍是注释模板；本清单是本地工程约束，不宣称远程保护已配置。
