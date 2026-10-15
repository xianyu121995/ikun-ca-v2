# C-03 Projects 只读评分 UDS 交付

夜间授权 `579a57f2e3e470525eb53f9f1f85ba75d25f3728`，按 B3 `4e0b293901c72df0c28180eb849a2d67d8c9c4c9` §6/7 和根补正实现。认证修复 `cc95dc27852d056457ca0582cff64a88c0eab1d4` 为直接祖先，依赖批准以 `967f3098e84de7e299d970019d56b571ac63de94` 为准。完整本轮SHA和提交后复验由交付消息及忽略的 `artifacts/c03-final-receipt.json` 绑定。

本域候选轻量回归通过，**等待总管按具体SHA审查**。未宣称B3 FeedPageV1/真实Next/公网或生产已通过，不把协议批准当作实现验收。

## 完成内容

- 仅在已有 `/v1/rpc` 新增 `operation=ratings` / `contract=tracking-ratings-v1`。B1真实principal沿原方向传输，两种既有角色可只读；无principal401，拒绝其他scope/role及不相关写字段。没有新HTTP route、worker回调、方向secret、服务或Projects迁移。
- body严格为0–200唯一canonical IDs及必填expected_catalog_version。空批核验全局版本；完整输出contract/catalog_version/checked_at/items，每项只含project_id/state/rating/revision；S/A/B/C/D/null、真实未评分和missing双null明确区分。主页移除/完成不丢canonical或评分，不改已有CRUD/commands/inbox/outbox语义。
- scope最大project_changes sequence、boot nonce和既有UDS凭据摘要形成64字符全局版本；校验与取行在同一SQLite读取事务。跨批变化/重启/受控恢复/方向轮换409 VERSION_CONFLICT；不把逐项目revision或当前页指纹当全局版本。
- Node helper对ratings强制整个调用2秒并传播取消；完整集合、唯一性、字段、found/missing和revision逐项核验，坏JSON/envelope/投影或源故障503 UPSTREAM_UNAVAILABLE，无部分成功。旧RPC超时和旧公共路由保持原状。
- 同域并发旧回归暴露SHM在is_file与第二次stat之间消失的路径检查竞态，改为单次lstat；保留符号/硬链接、非普通文件拒绝，补两项回归。不放宽存储归属或链接保护。

协议与批准原稿替代关系见 [tracking-ratings-v1.md](protocols/tracking-ratings-v1.md)、[机器清单](protocols/tracking-ratings-v1.json)。原f8a6bbc提案及B2报告、回执、失败现场均未改写。

## 文件范围

生产代码为 `candidate/projects_service/{transport,ratings,service,ipc,db}.py`、自有 `integration/website/lib/projects.ts`。回归为新 `test_tracking_ratings.py`、`ratings-ipc.test.mjs` 及已有 `test_b2_lifecycle.py` / `guards.test.mjs` 的实际入口补充。其余为本报告/协议/核验记录，全部在 `modules/projects/**`，无schema或其他owner文件。

## 测试结果

| 轻量回归 | 实际pytest数量 |
| --- | ---: |
| test_projects.py | 63 |
| test_b2_domain.py | 54 |
| test_b2_home.py | 23 |
| test_tracking_ratings.py | 46 |
| test_b2_lifecycle.py | 3 |
| test_b2_browser.py::test_actual_entries_without_proxy（不启动Next/浏览器） | 1 |
| **合计** | **190通过，0失败、0错误** |

两个wrapper内分别是14项真实UDS传输Node测试、11项真实B1/UDS入口Node测试，已计入190，不重复累加。认证同/跨模块回归3项另报通过；TypeScript strict/noEmit单文件通过。只有原Starlette/httpx TestClient弃用提示。

覆盖0/1/200/201、非法/重复ID、错误profile/写字段、user/admin、所有底层评级/缺值、201项目跨批、scope、无持久变更/只开Projects、同快照并发写、完成/恢复/成员移除、幂等重放、真实handler鉴权/版本/credential轮换。真实B0子/父强杀及正常重启3项都验证新catalog与旧expected拒绝。UDS真实socket测试验证两秒deadline、上游取消且没有重发，以及错误/重复/缺项/非法found和missing投影拒绝。

初次旧并发回归发现SHM竞态（原77项中的1项失败）；修复后122项领域回归通过。首轮190为189通过/1个wrapper失败，原因是新增Node测试排序了实际键却未排序期望键；修正后最终190通过。失败JUnit保留 `artifacts/pytest-c03-light-initial.xml`，后续最终记录为 `artifacts/pytest-c03-final.xml`，没有将失败覆盖成成功。

```sh
# 在 modules/projects/candidate 中运行，不含所有Next/Chromium案例
.venv/bin/python -m pytest -q tests/test_projects.py tests/test_b2_domain.py tests/test_b2_home.py tests/test_tracking_ratings.py tests/test_b2_lifecycle.py tests/test_b2_browser.py::test_actual_entries_without_proxy --basetemp=/private/tmp/ikun-c03-final --junitxml=../artifacts/pytest-c03-final.xml
# 最终提交后以真实HEAD绑定UDS，复验50项
.venv/bin/python -m pytest -q tests/test_tracking_ratings.py tests/test_b2_lifecycle.py tests/test_b2_browser.py::test_actual_entries_without_proxy --basetemp=/private/tmp/ikun-c03-committed --junitxml=../artifacts/pytest-c03-committed.xml
```

测试前仅将当前自有helper复制到忽略预览供tsx导出入口使用；没有执行完整build，该复制不使旧Next构建成为新构建。Node类回归/TypeScript命令见认证小修复报告。52个本轮源码/测试/SQL输入的SHA256集合为 `6fc9ef0895ea8d4e95709477d49d3852581d7893e5f9e6704fafb4a10533eee1`，逐项哈希及JUnit/传输日志哈希见 [c03-ratings-check.json](integration/evidence/c03-ratings-check.json)；该文件是源码/轻量测试证据，**不是完整构建receipt**。

## 待双方实际接线与限制

全部候选及监控统计ID的枚举、按S/A/B全量筛选计数、真实Tracking备注、60秒快照、ordinal游标及页大小变化、最终双版本核验、至多一次重取与8秒整体预算由B3现有BFF/controller按统一wire实现。本域没有读tracking.db来替其验证，也不把201项目投影测试冒充全量feed验收。

B3用固定Git导出当前依赖，连同已批准密码10 Auth f097bd4做实际Next303/401/静默SSE和FeedPageV1浏览器复验。完整build/浏览器如需执行须持主仓库唯一heavy lock，本窗口本轮没有运行。只用临时合成Projects和经已验收B1组件创建的临时认证夹具；不读写实际Hunter/Tracking/生产库，不执行真实平台/Watch/付费/采集或语音。没有合并、推送、部署或修改其他Worktree/正式apps/root/旧服务/Tunnel。
