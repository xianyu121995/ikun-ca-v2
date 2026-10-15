# B2 第一轮审查修订交付

对 `f89c58e639ca9d844ebead5d019c29f0476d5314` 的三项退回意见完成本地修复，向前提交，不改写原提交。最终完整 SHA 和提交后绑定复验结果由交付消息及忽略的 `artifacts/final-receipt.json` 记录。**待总管复审、正式收件；本轮不是 B2 验收或后续阶段放行。**

## 修复与回归

| 审查项 | 修改 | 真实回归证据 |
| --- | --- | --- |
| B2-REV-001 | `integration/website/lib/project-events.ts` 每个数据帧使用 `{data: ProjectRecordV2, request_id}`，保留 sequence id、`project.updated`、安全投影和 Last-Event-ID | 实际 Next GET 导出入口解析首帧和续传帧，断言标准包、合法请求 ID、16 个公开字段、真实项目内容和递增位置；取消读取后实际 UDS 请求计数不再增长。退出、禁用、过期、重置、改密的逐块/静默撤销继续通过 |
| B2-REV-002 | `candidate/projects_service/queries.py` 根据 cursor 键存在与否判断，省略才是首页 | 空串、空格、Tab、损坏 cursor 均 422；真实 HTTP `milestones?cursor=` 返回标准 422；正常分页无重复，跨 window/rating/limit 均拒绝 |
| B2-REV-003 | `projects-home.tsx` 和自有 UI 补丁共用 `canPage`；未知 cursor 和加载期间禁用导航，已知 cursor 可返回 | 1440/390 真实浏览器验证未访问的第 3 页 disabled，访问 3→1→3 成功，每页 ID 与独立 HTTP 游标查询逐条相同、选择清空；4 次导航只发 4 个主表页请求，没有多页预取/合并 |

附带修正两处测试同步/定位：页码测试等待实际目标 ID；原完成弹窗测试精确选择项目名称，避免将评分字母作为翻页标志。业务修改仅上述三项，未增加字段、接口或迁移，未改定稿布局/CSS/文案。旧 UI 分支和正式网站路径保持冻结。

## 最终测试

| 文件 | pytest 数量 |
| --- | ---: |
| test_projects.py | 63 |
| test_browser.py | 8 |
| test_b2_domain.py | 54 |
| test_b2_home.py | 23 |
| test_b2_browser.py | 11 |
| test_b2_lifecycle.py | 3 |
| **合计** | **162 通过，0 失败、0 错误** |

相对首版增加 7 项 pytest。实际入口 wrapper 内 10 项 Node 子测试全部通过，已经包含于上述 162 项，不重复累加。Node24.22.0 / Next16.4.1 完整串行生产模式构建通过。仅有原 Starlette/httpx TestClient 弃用提示，未改锁定依赖。

前两轮各为 161 通过、1 失败，保留在忽略的 `artifacts/pytest-rev1-initial.xml` 和 `artifacts/pytest-rev1-second.xml`；最终 JUnit 为 `artifacts/pytest-rev1.xml`。具体原因及最终分组/截图哈希见 [test-receipt.json](integration/evidence/test-receipt.json)。

```sh
# 在 Projects Worktree 根目录，重建固定依赖的隔离预览
B2_NODE='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node' modules/projects/candidate/.venv/bin/python modules/projects/integration/build-preview.py
cd modules/projects/candidate
.venv/bin/python -m pytest -q tests --basetemp=/private/tmp/ikun-b2-rev1-verified --junitxml=../artifacts/pytest-rev1.xml
# 提交后以真实 HEAD 绑定 B0/IPC，再执行包含全部新增用例的复验
.venv/bin/python -m pytest -q tests/test_b2_home.py tests/test_b2_browser.py tests/test_b2_lifecycle.py --basetemp=/private/tmp/ikun-b2-rev1-committed --junitxml=../artifacts/pytest-rev1-committed.xml
```

## 输入绑定与边界

48 个自有源码/测试/SQL 输入 SHA256 集合为 `c75259acfcd8f37cee1bdd05812f3e41bd5f901a862db071a2aba7ab7611547a`；构建、最终回归输入无漂移，见 [build-inputs.json](integration/evidence/build-inputs.json)。26 个固定 B0/Auth/UI 源文件均与固定 Git 对象及实际预览字节相同；原 [frozen-inputs.json](integration/evidence/frozen-inputs.json) 不变。所有依赖与 `phase2-v1.0.0+auth-b1-final-v2+projects-home-v1` profile 沿用首版。

UI 补丁 SHA256 为 `cf2f4058659811f93ede9776e226fe1d9336402e2e936aa25274fde3cf55bae2`。再次从定稿 `eb93ac7739e0ce9d74fa9859f838a7bca294ce3e` 独立导出两文件，`git apply --unidiff-zero --check` / apply 通过，结果与实际构建字节相同，见 [ui-patch-check.json](integration/evidence/ui-patch-check.json)。[1440](integration/evidence/homepage-1440.png)、[390](integration/evidence/homepage-390.png) 为最终轮合成数据截图。

首版 5 份构建/测试/补丁/截图证据归档于 [review-f89c58e](integration/evidence/review-f89c58e/)，全部与原提交对应文件逐字节相同；[原报告](B2-REPORT.md) 保留历史计数和哈希。

仅改 `modules/projects/**`；仅使用本域 projects.db，测试通过已验收 B1 组件生成临时合成认证资料。没有直接读写 Hunter/Tracking 数据库，没有 WSS/REST/NEW_TWEET 采集，没有真实 worker、平台或付费调用。

**正式网站收件、公网、真实 Hunter/Tracking 联调仍 BLOCKED。** 旧候选活跃身份退役升级限制、SIGKILL 后可能留下空临时目录等原报告限制保留。本地完整通过不能替代总管或实际部署验收。没有 merge/cherry-pick/rebase/reset/amend/push/deploy，没有触碰生产、旧服务、Watch 或 Tunnel。

运行隔离预览的方式见 [integration/README.md](integration/README.md)；本轮未启动常驻预览或创建持久 Auth 账号。
