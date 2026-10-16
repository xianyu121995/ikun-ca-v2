# Tracking 观察受理与持久回执交付

本轮按总管 `d7c0093c4dd3c09fc74faa2a44ede073e32bca72` 批准的协议实现，128KiB 补正提交 `c8fb68901db9d4b00300ef483c8d20f9de33f7c6`；Projects 基线 `aa51a640a159e4c8f6cdd841a25f4279e73075ba`，输入锁定 Tracking `c4de379a67bd9b154bab87ce81d4645b53102ea0`。完整实现 SHA 由交付消息和忽略的 `artifacts/tracking-ingest-final-receipt.json` 绑定。

网站候选受理/查询回执及轻量回归通过，等待总管按实现 SHA 正式收件。未合并、推送、部署，未升级或启动冻结 worker。原 B2/C03 报告和证据保持原样。

## 完成内容

- 原 `POST /internal/v1/ingest/tracking` 从501改为独立观察接收；沿用 `PROJECTS_INGEST_TRACKING_TOKEN`、已有网站→Projects UDS 和 `tracking-observations-v1` 私有 RPC。GET 原 `/internal/v1/receipts/tracking/{event_id}` 可查询持久回执，不增加服务、bus、方向凭据或公开 API。
- 严格接收 c4de 的10字段 envelope / 15字段 activity，仅两种 created/updated 类型。校验 canonical/sub/event ID、固定 namespace 的 activity UUIDv5、内外项目/时间/correlation、X URL/handle/tweet、实时与更正标志；保留合法 updated unknown/reply/repost。
- Tracking HTTP 专用128KiB，Hunter仍64KiB，既有IPC仍131072字节。仅Tracking解析使用 Node24.22 的 JSON reviver context.source / rawJSON 保留原数值语义，正int64最大值不被JS浮点舍入，1.0也不被改造成整数。严格UTF-8和Unicode scalar，拒绝非法UTF-8/单surrogate，不截断正文或修补hash。
- 原已校验对象按 c4de Python canonical 算SHA256，保留原时间字符串与数值；可选私有 `X-Expected-Event-SHA256` 在POST核对原事件、GET核对已存hash。格式错422，hash冲突409，同ID/hash返回原receipt_id和首次accepted_at。
- `BEGIN IMMEDIATE` 内复用 `event_inbox` / `project_sources`，只建立 `observations-v1:subscription:{sub_ID}`→已有同scope canonical关联并写最小回执；无/外scope项目404，订阅改绑409，失败整事务回滚。原EventReceiptV2六字段保持，Tracking command_id=null。
- 不存 envelope、正文、名称或URL，不新增项目，不改人工字段/评分/研究进度/主页成员/revision，不写命令/project_changes/公开SSE，不改变C03catalog。hidden/removed/C/D/未评分不会因观察自动加入主页。
- 原方向身份检查独立于Proxy；cookie/伪造角色无授权，错误方向401，已认证source/scope冲突403，已知方向凭据复用配置拒绝503。错误仅error/request_id，统一no-store，不返回伪造成功。

## 修改文件

运行代码仅 `candidate/projects_service/{tracking_observations,service,transport}.py` 和自有 `integration/website/lib/projects.ts`；测试新增 `candidate/tests/test_tracking_observations.py`、`integration/tests/tracking-ingest.test.mjs`。其余为README、本报告、源码/测试证据JSON。全部在 `modules/projects/**`；schema版本2、两份正式SQL及校验和未变，无迁移、依赖或根配置变化。

Auth live constructor包装、C03评分校验/两秒调用段、原Hunter领域事务、主页组件/公共API/页面布局均保持基线字节；原Hunter真实HTTP受理/查询/重放回归通过。未读写其他业务数据库，夹具只创建 `/private/tmp` 合成 Projects 库；B1原入口回归使用其已有临时认证夹具。

## 测试结果

| 轻量回归 | pytest通过数 |
| --- | ---: |
| test_projects.py | 63 |
| test_b2_domain.py | 54 |
| test_b2_home.py | 23 |
| test_tracking_ratings.py | 46 |
| test_b2_lifecycle.py | 3 |
| test_b2_browser.py::test_actual_entries_without_proxy | 1 |
| test_tracking_observations.py | 56 |
| 合计 | **246，0失败、0错误** |

三个wrapper内分别含C03真实UDS14项、B1/UDS实际入口11项、Tracking实际route/UDS/Python及HTTP16项，已计入246，不重复累加。跨模块认证回归另3/3；TypeScript strict/noEmit单文件通过。仅既有Starlette/httpx TestClient弃用提示。

新增覆盖：严格wire错误26组、合法创建/更正7组、12并发重放、顺序无关hash/异hash409、原时间表示、source/scope与已存canonical、订阅冲突、alias后故障的整事务回滚、移除/隐藏/评级不变、无正文落库、实际IPC鉴权/build/principal。Node真实入口覆盖最大emoji/控制字符及int64、1.0拒绝、超限/UTF-8/surrogate、Hunter原路径、真实HTTP commit后断开响应再GET原回执、真实HTTP存储故障503后GET404、managed IPC实际重启后GET同receipt。临时Projects库和仍存在的WAL检查没有原观察正文marker；仅Hunter回归产生原有命令。

```sh
# cwd: modules/projects/candidate；仅轻量入口，不启动Next/Chromium
.venv/bin/python -m pytest -q tests/test_projects.py tests/test_b2_domain.py tests/test_b2_home.py tests/test_tracking_ratings.py tests/test_b2_lifecycle.py tests/test_b2_browser.py::test_actual_entries_without_proxy tests/test_tracking_observations.py --basetemp=/private/tmp/ikun-ti-final-light --junitxml=../artifacts/pytest-ti-final-light.xml
# 提交后按真实HEAD绑定IPC复验；结果另写final-receipt
.venv/bin/python -m pytest -q tests/test_tracking_observations.py tests/test_b2_lifecycle.py tests/test_b2_browser.py::test_actual_entries_without_proxy --basetemp=/private/tmp/ikun-ti-committed --junitxml=../artifacts/pytest-ti-committed.xml
```

源码清单、逐项hash、JUnit/TAP hash及命令见 [tracking-ingest-check.json](integration/evidence/tracking-ingest-check.json)。预览仅复制当前自有helper给tsx导出入口使用；本轮未完整build或运行浏览器，不把旧Next构建作为本轮构建。没有测试失败被覆盖为成功；协议静态size检查及原阶段失败记录保留。

## 运行与未闭合范围

集成方按正式收件SHA导出自有网站helper/Projects包，沿现有B0托管和原方向token配置运行；初始化与独立预览方法仍见 [integration/README.md](integration/README.md)。本增量无需迁移或填入新凭据；这里只说明运行条件，不触发集成/部署。

c4de worker尚无 delivery/claim/ACK/reconcile 写回任务。网站受理与可查回执不等于tracking.db pending已清零；本窗口没有替worker补任务、读其数据库或宣称真实端到端成功。Tracking原owner后续需在原单实例lease内实现受控loopback投递、原hash核验和本库持久ACK/重启恢复，并协调D2 purge；须由总管另行放行。

过期scrub对象POST422；原hash GET200只证明历史受理。无原回执404继续unknown/expired_pending_reconciliation，不伪造ACK或终态、不重建正文/新ID、不从SSE补投。现有wire无权威全局expires_at，不能用新generation received_at重推15天寿命；本域无新内容投影，也未证明完整TTL闭环。B3展示/语音、真实worker投递、本地pending写回、实际Next/公网集成及部署验收仍分别由原owner承担。
