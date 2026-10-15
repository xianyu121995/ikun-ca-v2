# B3 本地回执与新协议送审 · 2026-10-16

结论：**PARTIAL / pending_protocol_review**。旧 B3 跟踪业务本地回归、独立运行、最终构建及1440/390业务流程通过；固定Next认证组合500使整体AUTH验收仍BLOCKED。新产品方案已批准，本交付只提交精确协议，未实现/验收新D1/D2/C01/C03/C05。无合并、推送或部署。

**当前完整构建和Chrome继续暂停。** 依据用户最新转达的Claude资源优先通知，仅整理代码、证据及必要轻量检查；等待项目总管或Claude明确解除。以下构建、compiled及浏览器结果是已存在的历史批次，本轮没有重跑，也未获最终验收放行。

## 提交与输入

| 对象 | 完整 SHA / SHA256 |
|---|---|
| 原候选代码及轻量检查点 | 2c7ce9a36350aa438c8d197b60d41de2b4aa1c96 |
| 版本化协议提案（只含2文件） | 4e0b293901c72df0c28180eb849a2d67d8c9c4c9 |
| 本轮受测业务/接线修复（11文件） | f8e8f9101dbbe6e85d20847cd10c7d3eddffbd30 |
| 最终运行/测试/工具源集合（50文件） | 8bc839b2aa8dd838d50560bb6e74cea6aa053eb784ab7934d8e61b85fd31c87d |
| 预览冻结+覆盖输入（327文件） | 07571e7e8432596b9515915520676ffeaf90315f1ddec601ccc13cbbb1919c72 |
| Next BUILD_ID | JzEPmMz6lFoVlV1ziEm9_ |
| 最新产品权威 / 政策 | 50ee277aed435a723aab6139bd952e709b3ad08e / product-decisions-v1.1 |

source_inputs逐文件与f8e8f91的Git blob和工作树比对通过；build-inputs和browser receipt的源集合/BUILD_ID一致。全部文件/日志/截图/锁收据SHA256在B3-EVIDENCE.json。交付文档的后续提交不改变受测运行源集合。

本轮轻量完整性核验：50个源码文件同时匹配工作树与受测Git提交，327个预览文件匹配构建清单，18份日志/回执哈希匹配，JUnit确认89项无失败/跳过，提案与产品权威文档哈希匹配。记录在B3-EVIDENCE.json的current_lightweight_verification；本轮没有重跑pytest、构建或浏览器。

固定依赖继续是spec 9699375c920465b5d802e7acff17b5421203e544、B0 85be3bd6dce25d82033b6cb1a7157aaa39bd571e、B1 28e6aaf4141790fc74ae4ae4429be4b854460955、B2 d0fdefab2aa230ebb8df856aed306d0184d362e2、公共UI 486294ac3255b08fdb13a307ee15f96c571020d9、Tracking UI d90598f4bc595458ce26c5ee1c2e1618e318abc0。使用Git对象导出，不引用浮动Worktree、不改旧冻结清单。密码10增量f097bd4722155d5e689b8894956391ed7e5f2fa7及1d56ef2f003c531574e41fe079c70510ac6ed437审查已读取、单列记录，未代改Auth或混入本次固定输入。

## 本轮实际修改

- `integration/website/lib/tracking.ts`：不再构建/替换B1 singleton；仍执行实际B1角色、scope、CSRF、页面与Action guard；SSE使用已冻结events/stream候选入口。
- `integration/website/lib/coalesced-refresh.ts`、controller：一个活动刷新加一个合并后续刷新；修改成功后等待新revision，不丢弃刷新，不无限排队；旧页面的在途响应不覆盖新页面。解决实际捕获的“PATCH200后stop携旧rev→409”。
- `integration/patches/tracking-live.patch` / sync：保留批准布局/CSS，仅修真实原文、刷新、管理说明等live文案。标准SSE接线在自有integration；候选仅Tracking流，多来源最终组合归集成owner。
- 测试脚本：按实际DOM定位表单，窄屏媒体隐藏按冻结CSS验证；1440与390都有真实本库推文。补真实Next停启后持续入库、失败现场与明确PARTIAL状态。
- 原独立引擎/commands/租约/迁移/远端核验/600配额/重试/去重保持；本轮没有重写引擎或新增平台调用。

所有修改在services/tracking-worker与schemas/tracking自有范围。本轮没有改Auth/Projects源码、根依赖/契约、正式apps/website、公共UI、旧版服务或共享Watch。preview位于本模块忽略目录，不是其他Worktree。

## 实际验证及计数

| 验证 | 命令 / 证据 | 实际结果 |
|---|---|---|
| 最终Python全量 | `.venv/bin/python -m pytest -q --junitxml=...`；python-b3-final-1792083352262229000.log及XML | 89通过，0失败/跳过，19.69s；1条TestClient/httpx弃用提示 |
| Node实际入口及队列 | 由tests/test_node_entries.py执行Node24+tsx；node-entries-pytest-1792083369026449000.log | 7通过；包含在上述1个wrapper，**不算89+7** |
| 最终串行构建 | `integration/build-b3.py`；build-9.log/build-inputs.json | 5步通过：shared、UI、Auth tsc、Tracking、Next；327输入前后相同 |
| source生命周期 | `node integration/tests/lifecycle.test.mjs --source` | 显式init、SIGTERM=0、父SIGKILL回收、重启通过 |
| compiled生命周期 | `node integration/tests/lifecycle.test.mjs`；lifecycle-compiled-1792083071195452000.log | B0实际service.mjs/compiled入口相同四阶段通过 |
| 真实Chrome | `node integration/tests/browser.test.mjs`；browser-1792083074052/receipt.json | completed=true，tracking_flow_passed=true，整体passed=false，exit2 |
| 浏览器细分 | 两种宽度11组：8通过、3组认证阻断，相关500响应5次 | 非auth跟踪操作均通过；pageerror=0；没有把失败软标PASS |
| 静态/视觉 | Ruff、Git hygiene、TS/浏览器脚本语法；实际查看2截图 | 通过；备注在前、无页面横向溢出、窄屏按定稿隐藏媒体栏 |
| 协议静态校验 | JSON解析、Markdown SHA、5个验收ID映射、3份权威文档Git SHA256 | 通过；仅提案结构/来源验证，不是新功能测试 |

pytest分组：api_store25、config10、identity1、lifecycle26、Node wrapper1、processes1、schema23、v1/lease2，总和89。旧41覆盖替代沿用2c检查点：26旧引擎项保留，API/身份getter成功用例被方向API与实际B1入口替换，schema/lease/进程覆盖扩充。旧quote排除/超过7天保留等只代表legacy候选，不作为新D1/D2证据。

浏览器通过的跟踪流程：人工确认→ACK假成功unknown→真实夹具远端读回；编辑→立即停止→恢复；去重/刷新持久/真实备注在账号与正文前；未知媒体/互动/重要标记不伪造；安全原文链接仅本地拦截；删除订阅经API比对主页未改；真实Next退出后emit新推文仍入tracking.db，重启后网页查回；普通用户伪造角色写入403。所有provider数据为MockTransport/loopback，X原文由测试拦截，真实provider调用0。

## 重任务锁及失败保留

既有完整构建、compiled/Chrome批次和完整preview生命周期，均通过同一主仓库脚本；当前暂停期间不执行，明确解除后仍使用该唯一脚本：

以下在本python目录执行；最终批次按同一前台调度依次执行三项，任一非0即保留该退出码：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py \
  --owner tracking-worker --timeout 600 -- .venv/bin/python - <<'PY'
import subprocess
import sys
node = '/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node'
for command in [
    [sys.executable, 'integration/build-b3.py'],
    [node, 'integration/tests/lifecycle.test.mjs'],
    [node, 'integration/tests/browser.test.mjs'],
]:
    result = subprocess.run(command, timeout=240)
    if result.returncode:
        sys.exit(result.returncode)
PY
```

已保存7个既有锁批次：1个独立构建成功、5个历史失败批次、1个最新PARTIAL。最新收据 `tracking-worker-ef5b34a1-602e-49a1-9cd7-044f1485eb4f.json`，exit2；原始路径在主仓库var/coordination，本模块有逐字副本及SHA256。没有第二把锁、删锁、抢并行或提前释放预览锁。旧build-1/a11a80a1只作过期历史，不当最新构建。既有锁收据不能替代当前暂停的解除通知。

历史失败原因及修复：登录标签误配→依据实际DOM修脚本；必填星号影响exact label→按表单字段/可访问角色定位；窄屏媒体按CSS隐藏→修正测试可见性断言，不改UI；实际PATCH后旧revision409→合并刷新队列，补网络屏障/并发/失败恢复回归；认证500→保留真正依赖阻断。所有日志、failure.html/png/state均保留，没有覆盖成成功日志。

## 当前 P0 与新裁定覆盖

| ID | 当前结论 / 证据 |
|---|---|
| TRK-01 | legacy本地远端核验、600、noop/timeout/未知与重启通过；真实平台未验 |
| TRK-02 | 失败不假停止；两尺寸真实API启停恢复通过，刷新竞态已修 |
| TRK-03 | legacy同代去重/正文补全/备注在前通过；**不冒充新D1/C01/C03/C05** |
| AUTH-01/03 | **BLOCKED**：固定Next组合后匿名/禁用旧Cookie出现5次500；预期页面303、API401；无业务data但不能签收 |
| AUTH-02 | 普通用户业务写403在Node与两尺寸浏览器确认；不代表整个Auth集成已通过 |
| ISO-01 | Tracking仅本库；通过owner API的私有夹具核对移除不改Projects；无跨库SQL |
| OPS-01 | source/compiled guardian与真实Next退出后引擎继续运行通过；不宣称生产三服务验收 |
| OPS-02 | 无部署、无旧资源改变；公网/实际生产未验 |
| DEC-D1 | 产品已确认：原创+引用任何对象，排除转推/回复/未知；4e0b293提案已含WSS/REST及三类引用矩阵，**pending_protocol_review**，raw适配证据待固定 |
| DEC-D2 | 15天/先备份/永久小账本/恢复已提精确边界，**pending_protocol_review**；未运行清理或004迁移 |
| DEC-C01 | 新profile全量发布时间排序/未知回退/绑定cursor提案，**pending_protocol_review**；旧默认未改 |
| DEC-C03 | 真本地备注+Projects只读评分/SAB全量计数分页提案，**pending_protocol_review** / **pending_owner_implementation**；双方SHA尚未冻结 |
| DEC-C05 | 稳定act_ID/sub+tweet折叠/单事件/跨代及清理后去重提案，**pending_protocol_review**；尚未实现 |
| D6/D7/D8 | 产品已定，语音仍held；无播报代码或“语音PASS” |

C01/C03/C05不再等待产品裁定，而是等待已授权方案的精确协议与实现审查。提案代码门禁为真，不因方案批准自动实现新接口。

另有B2 ingest/tracking=501，观察outbox仍pending/可查，无投递成功假回执。认证问题的实际现场、隔离诊断及未应用owner修复方向在AUTH-NEXT-BLOCKER.md；当前只修本模块，不偷改固定依赖。下一步由总管审查4e0b293并与Projects对齐C03，依赖owner处理认证组合，再在获批范围前向实现并复验。本地结果不能代替真实6551、跨worker、受保护域名或生产验收。
