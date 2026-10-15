# HunterRadar 已有成果冻结 · 2026-10-15

状态：**独立候选已冻结，整体正式集成未验收，不可据此上线。** 本次只保存已有成果、已有测试和交接信息，不继续业务开发、硬化、接线或接口变更。冻结检查仅清除 HTML 一处空白行的行尾空格，无业务变动。

## 基线、范围与提交

- Worktree：`ikun-ca-v2-worktrees/hunter-worker`；分支：`codex/hunter-worker`。
- 原基线：`f89d8f55fc3e68d6360e7a1e33e23bde48591098`，`foundation-v0.1.0`。
- 提交仅包含 `services/hunter-worker` 与 `schemas/hunter/002_hunterradar.sql`。
- 冻结提交完整 SHA：提交后执行 `git log -1 --format=%H`；以本文件所在提交为准，避免在提交中写入自身 SHA。
- 提交内容和工作区核对：`git show --stat --oneline HEAD`、`git status --short --branch`。
- 不修改根依赖/锁文件、contracts/runtime、其他窗口文件或生产服务，不合并、不推送、不部署。

## 已有实现

Python 3.11 独立引擎、hunter.db、FastAPI 业务 API、真实存储页面和接入候选。Node 24 启动入口只有显式 `HUNTER_ENGINE=python` 才通过 execve 替换当前 Hunter 进程；不增加第四个正式服务。默认仍保留基础骨架入口，外部 IO 默认关闭。

- 查询猎手稳定 X ID 与粉丝数；≥5000 为 WSS，<5000 为 REST，未知身份保持 pending。
- WSS 订阅确认、应用 heartbeat、超时重连；方向为外层 twAccount → content 内目标，支持 JSON 字符串 content。
- REST 每小时读取最新 20 个 Following，首次仅建基线；已见目标持久去重，满页/轮询间断提示漏采风险。
- 72H 内按不同猎手稳定 ID 聚合；WSS 用事件时间、REST 用首次观测时间，不伪造 REST 精确关注时间。
- 本地猎手增删、备注、启停、版本冲突保护；软删除保留历史，通道/生命周期 generation 阻止旧请求落库。
- 数据库内 worker 租约、原子写入与崩溃恢复；每日额度预留、速率限制、并发上限、失败退避。
- 模糊计费超时记为 provider_billing_unknown，不自动继续该付费请求。
- 人工确认后才创建 outbox；固定幂等标识，项目回执验证。v2 事件候选在发送前查询 receipt；不明确时保留 unknown，不能直接作为已接收。
- 已确认 UI 的独立文档版本接真实 API；资料、评分、备注和猎手操作写 hunter.db。网站页面/BFF 模板只作为候选保存在本模块，未修改网站窗口文件。
- 仅打开自己的 hunter.db；无 tracking.db/projects.db 读写、无 ATTACH、无远端 Watch 增删/覆盖调用。

冻结暂存检查：40 个文件全部位于 Hunter 所有权路径；未纳入 DB/WAL、凭证、venv、node_modules、var 或构建产物；秘密格式扫描零命中，暂存区 diff --check 已通过。提交 hook 保持启用。

## 已有验证证据

| 检查 | 真实结果 | 证据 |
| --- | --- | --- |
| Python 单元/API/存储/恢复/MockTransport | 69 passed，0 failures，0 errors | `python/docs/test-results.xml` |
| 浏览器交互 | 11 组 passed；Chrome；390/768/1440/1920/2560px | `python/docs/browser/results.json` |
| 进程 smoke | 3 次真实 OS 启动、优雅重启、SIGKILL 后等待租约过期恢复；猎手 ID 保留 | `python/docs/process-smoke.json` |
| 外部调用 | 上述 smoke 外部 IO=false，provider_requests=0 | 同上 |
| Node 24 | frozen-lockfile 安装、build:shared、Hunter typecheck/build 已通过 | 本聊天执行输出；不把基础包 build 当作业务验收 |
| Python compile / JS syntax | compileall、node --check 已通过 | 本聊天执行输出 |
| SQL 副本 | Python schema 与 002 SQL 字节一致 | 本次冻结只读核对 |
| Git diff --check | 冻结前执行；提交前再核对暂存区 | 提交执行输出 |

测试中先前的两个问题：macOS 对 DB 文件加 flock 导致 SQLite 锁冲突，已改为数据库内租约；浏览器严格定位和异步提交等待已修正，最终结果为上表。`python/docs/browser/failure.png` 是保留的早期失败截图，不是最终验收截图。

Starlette TestClient 有一条 httpx 弃用警告，测试通过；未为消除警告新增依赖。

## 未验证、接口差异与发布阻断

1. **真实来源未验收。** 没有配置第三方凭证，没有付费 API、真实 WSS、新增关注手工实验或真实账单核对；模拟测试不能证明平台完整覆盖。
2. **WSS Watch 覆盖依赖。** 新增本地猎手不等于远端已覆盖；只读检查 existing Watch，缺少 newFlwBol 覆盖须由持有独立授权的配置流程解决，本模块不修改共享 Watch。
3. **正式页面/BFF 未合并。** 模块私有路由 `/api/hunterradar/v1/*`、epoch 时间/offset 分页，与共享 `/api/v1/hunter/*`、标准 envelope、ISO 时间、opaque cursor、If-Match 和所有写入幂等规范仍有差异。页面隔离接线通过不等于正式 Next/BFF 或真实登录验收。
4. **认证必须由网站提供。** `integration/next/gateway.ts` 和 Python gateway 要求注入真实 session/权限校验；只认可 superadmin/user 的账号规范。当前服务内部的 admin/viewer token scope 不是认证用户实现。v2_mode 无服务 token 时关闭本机免密回退。
5. **共享内部 command/events 适配尚未完成。** 只具备 health/status 的基础兼容和模块私有业务 API；不能称完整符合正式内部 command inbox/events 协议。
6. **项目接收联调未验收。** v2 EventEnvelope 和 receipt 查询只有 MockTransport 证据，`hunter.project_monitoring_requested` 及 payload 需项目 owner/总管评审。canonical project_id 由接收方返回；目标用户名仅为候选键，不能当 canonical ID。收到任务回执也不能宣称已开始项目监听。
7. **其他保留限制。** 最新 20 条、停机缺口和目标改名可能影响覆盖；REST 差分不能识别所有取关后再关注。身份冲突不擅自合并。
8. **最后一轮硬化被自动审批拒绝，未执行。** 被拒动作包括：统一内部 HTTP 错误格式、未实现内部路由明确关闭、WAL/SHM 硬链接附加防护、v2 短服务 token 检查和创建空 `.env`。理由是审批系统把其他聊天的“仅 UI 原型”范围用于本聊天；重核原始授权后仍被拒。不得把这些补丁写成已完成，也未尝试绕过；按本次收尾要求停止新修改。`.env` 实际不存在，仅交付空值 `.env.example`。
9. **部署未执行。** 未安装 LaunchAgent、未启动付费采集、未改 Tunnel、未切换站点或旧监控。

## 启动与复现参考（仅记录，不在冻结中执行）

独立候选目录 `services/hunter-worker/python`：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt -e '.[test]'
cp .env.example .env
.venv/bin/python -m hunterradar run
```

本机页面为 `http://127.0.0.1:8766/hunterradar`，外部 IO 默认关闭。凭证只在本地编辑，不发送到聊天。引擎可随服务运行，不依赖网页打开。只有完成来源配置、契约评审及明确启用后才设置 `HUNTER_EXTERNAL_IO_ENABLED=1`。

v2 Worktree 根目录已有构建后的入口，显式选择 Python 实现的命令候选：

```sh
HUNTER_ENGINE=python /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node --env-file=.env.local services/hunter-worker/dist/main.js
```

以上使用已验证的只读 Node 24 开发工具链；正式部署不能依赖开发目录工具链。DATA_ROOT 由服务端配置，存储落在 `<DATA_ROOT>/hunter/hunter.db`，本 Worktree 分配端口为 3311。正式接入仍受上列阻断约束。

已有测试命令为 `.venv/bin/python -m pytest -q --junitxml=docs/test-results.xml`、`node tests/browser.cjs` 与 `.venv/bin/python scripts/process_smoke.py`。浏览器脚本需要 Playwright 和本机 Chrome，且默认只访问隔离 fixture 服务；进程 smoke 强制关闭外部 IO并清空来源凭证。

## 保留现场

- 原根目录 Python 候选、其他窗口/原型目录全部保留，未删除或覆盖。
- 当前 Worktree 的 `.venv`、node_modules、dist/shared 构建产物、var 内合成 hunter.db/进程 smoke 数据均忽略，不提交。
- 测试截图全部是合成数据。日志、DB/WAL、运行态、真实凭证、浏览器存储不提交。
- 独立预览服务会在冻结收尾停止；旧版监控从未停止或重启。
- 后续新增业务、硬化和正式接线须等总管规范与放行；本提交不代表接口审阅通过。
