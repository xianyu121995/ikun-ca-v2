# 主页项目领域

B2 现有实现已在原候选上增加 `phase2-v1.0.0 + auth-b1-final-v2 + projects-home-v1` 适配，入口与运行方式见 [integration/README.md](integration/README.md)，验收记录见 [B2-REPORT.md](B2-REPORT.md)。正式候选由网站通过 B0 私有 UDS 托管；原候选独立登录/TCP/offset 页面仅作历史回归，不作为新版入口。

本模块由“再做项目管理”窗口负责，分支 `codex/projects`，基础 `f89d8f55fc3e68d6360e7a1e33e23bde48591098`。

可运行候选见 [candidate/README.md](candidate/README.md)：独立 projects.db、迁移、CRUD、评分/简介/官网/备注/研究进度、真实搜索/排序/筛选/分页、受控加入、稳定 ID、来源去重、权限/租户、审计及页面测试。

人类角色仅 `superadmin/user`；所有人类业务写入仅 superadmin。服务身份单独绑定来源/租户，只能接受用户明确加入的资料，不能登录主页或调用普通 CRUD。不读取或修改 hunter/tracking/监控数据库，不承担采集。

**候选不是主站 READY。** Python 运行方式、正式 auth、公共 /api/v1/ 与内部 ingest、最终 UI 接线均需在既有三服务架构内集成；差异和待验收项见 [INTEGRATION.md](candidate/docs/INTEGRATION.md)。本提交不修改共享契约、根依赖/锁文件、网站入口或其他模块。
