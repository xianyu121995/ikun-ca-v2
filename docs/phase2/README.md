# ikun.ca 第二阶段冻结规范

版本：`phase2-v1.0.0`。由用户授权技术总管统一规范、协调冻结和分批放行。此版本仅冻结接口与规则，不合并业务、不安装生产服务。规范 Git 提交由同名 tag 定位，完整 ID 使用 `git rev-parse phase2-spec-v1.0.0` 查询。

## 权威文件

- `API.md`：HTTP、DTO、ID、权限、手工操作与回执协议。
- `DTO.md`：各请求、公开列表和页面投影的字段。
- `STORAGE.md`：四库归属、迁移、三服务生命周期与私有 IPC。
- `UI.md`：共享组件、字段、导航、展示权限与 UI 验收。
- `OWNERSHIP.md` 与 `ownership.json`：每个窗口可修改的目录与保留文件。
- `RELEASES.md` 与 `releases.json`：立即放行名单、后端依赖顺序和验收门槛。
- `contract.json` 与 `packages/contracts/src/phase2.ts`：机器可读字典与传输类型。
- `source-freeze.json`：9 个已有候选的完整 SHA 与冻结状态。
- `freeze-manifest.json`：权威文件的 SHA256。`node scripts/check-phase2.mjs` 校验内容、所有权和放行状态。

第二阶段采用这些文件；根 AGENTS/API/ARCHITECTURE/OWNERSHIP/HANDOFF/GIT 与之保持一致。第一阶段类型和历史审计是旧状态记录，不作为新功能的最终协议。文档和类型描述目标行为，不能据此宣称 routes、业务迁移或真实认证已经实现。

## 本轮放行

立即放行：全站UI设计、主页UI设计、猎手监控UI设计、猎手项目监控UI设计。范围是公共展示组件与不冲突的独立 UI、回调、视图适配和测试，不能自行接真实业务、操作数据库、补采集或修改全站入口。

尚未放行：认证、项目领域、Tracking、Hunter 的新后端工作，以及集成/发布。三个曾未冻结窗口已经提交已有成果；冻结不等于验收。认证 `aa3cf65` 仍含密码表单 P0、最终回归与浏览器检查缺口。Hunter 仍有自动审批拒绝的硬化未执行；集成证据只证明基础构建与工具，不能替代完整业务链路。

## 采用规范

各窗口在原 Worktree 读取主仓库的本版本或用 `git show phase2-spec-v1.0.0:docs/phase2/README.md`。本轮不 merge、cherry-pick、rebase、reset、push，也不替其他窗口复制/重写业务。自己的分支已有成果保留在 source-freeze 的 SHA；新 UI 改动由本窗口另提交，不覆盖冻结记录。

需要共享类型、依赖或全站接线时，先在本窗口交接文件列出需求；总管另行批准规范传播与基础设施候选。此轮不能把共享源目录或 node_modules/var 建成可写软链接。UI 可以定义纯展示 adapter，通过 props/callback 接收数据，适配器实现留在领域窗口。

任何后端阶段完成条件后仍需总管记录明确放行，不能自行把 `held` 改为 `released`。用户对“禁止擅自合并和生产部署”的指令持续有效。
