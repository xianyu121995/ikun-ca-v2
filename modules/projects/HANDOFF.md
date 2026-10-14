# 主页真实项目管理交付

2026-10-15；分支 `codex/projects`；基线 `f89d8f55fc3e68d6360e7a1e33e23bde48591098`。

状态：**隔离业务与页面测试通过；主站集成待完成。** 未合并、未部署、未运行生产迁移。只提交 modules/projects 与 schemas/projects。

## 本次结果

- 独立 `projects.db` + 两份带校验和迁移；本地空库已创建，integrity_check=ok，foreign_key_check=0。
- 新增、查询、编辑、删除；评分、简介、官网、备注、研究进度、日期均有真实落库逻辑。
- 数据库端搜索、6 种排序、评分/进度筛选、总数和分页；无演示数据回退。
- 受控明确加入、固定来源/租户服务凭证、canonical `prj_<UUID v4>`、来源唯一映射、官网去重、导入回执、失败回滚和并发去重。
- 删除只留本库 tombstone，不查询/删除上游，不发送采集或删除任务；重复导入不复活。
- 人类角色只含 superadmin/user；user 只读，superadmin 管理项目。服务身份只能调用本来源加入/回执，不能登录或操作普通 CRUD。
- 服务端租户隔离、CSRF/Origin、会话过期/撤销、限流、48KiB body 上限、稳定错误、请求 ID、版本冲突和审计。
- 三段八列 UI 已连真实候选 API，含错误提示和持久化验证；不冒充另一窗口最终确认的新版 UI。

## 验证

- **71 passed，0 failed，0 skipped**；其中 API/DB 63 项、真实 Chromium 8 项。
- 临时 Next.js 16.4.1 代理 + Chromium：同源登录、权限拒绝、新增、刷新、删除、退出通过。
- 本 Worktree 独立 pnpm install --frozen-lockfile、pnpm build:shared 通过；JS 语法、Python compile 和 git diff --check 通过。
- 一条非阻塞警告：Starlette TestClient 提醒后续改用 httpx2；当前测试通过。
- 证据：[validation.json](candidate/docs/validation.json)、[JUnit](candidate/docs/test-results.xml)、[页面截图](candidate/docs/homepage-fixture-1440.png)。截图仅为临时 Fixture 数据。

## 运行

目录：`modules/projects/candidate`；执行 `./run-local.sh`，访问 `http://127.0.0.1:8120`。本机登录凭证是该目录忽略的 `secrets/local-superadmin.json`，权限 0600；不在 Git/报告/聊天中包含 token。新 clone 的安装、迁移与凭证生成步骤见 [README](candidate/README.md)。

默认开发库 `candidate/data/projects.db` 只有一个本机 superadmin 凭证，没有项目、没有测试资料。旧的自建 homepage-projects Worktree 保留，未重置/删除；它不是正式提交基线，也不应运行其中旧权限模型替代本候选。

## 主站接入边界

Python 候选未成为第四个正式服务；Next 入口仅为待整合文件，没有改动 apps/website。最终新版主页 UI、正式 auth session、公共 v1 envelope/cursor/ETag、内部 event/receipt DTO 和唯一迁移器需总管组合验收。差异、代理复现命令和准确配置见 [INTEGRATION.md](candidate/docs/INTEGRATION.md)。

shared contracts 不同文档仍有 viewer/editor/admin 的旧描述，本候选按最新 HANDOFF 强制 superadmin/user；没有自行改共享类型。正式用户身份必须由 auth/BFF 提供可信接口，不能把候选本地凭证当生产账号。

未读取/修改 hunter.db、tracking.db、监控库或其 WAL；未调用 Watch、WSS/REST/NEW_TWEET、付费服务；未重启既有服务、未改 Tunnel。正式主站与生产尚未验收，不能标记 READY。
