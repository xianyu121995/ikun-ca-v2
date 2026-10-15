# Tracking B3 本地验收交付

候选源码提交：`c4de379a67bd9b154bab87ce81d4645b53102ea0`。本窗口交付代码、正式页面接线候选与本地证据，等待总管冻结/集成；未合并、推送、部署或启用真实来源。

## 完成内容

独立NEW_TWEET Worker、tracking.db显式迁移、人工确认项目接收、命令幂等/revision、远端实际回查后的启停/恢复/移除、600名额不足、接口超时/退避、WSS重连与重启恢复；网站停止时独立引擎仍入库。查询API和冻结UI候选接入真实本地BFF/Auth/Projects IPC。

published-v1服务端全量S/A/B筛选、计数、排序、分页；原创/任意引用、未知/回复/转推排除；跨代去重，15天先备份再清理，永久最小账本与带水位的显式恢复。修复恢复激活窗口、原子单调时钟、评分取消并发、sidecar竞态、429正文提前取消及游标错误流未关闭。

只在services/tracking-worker和schemas/tracking开发；001—003 SQL原字节不变，新增004。业务代码不访问hunter.db/projects.db，测试中的Projects库由固定Projects自有CLI/IPC管理，未直接执行跨库SQL。旧共享Watch未改。

## 实测结果

| 范围 | 结果与边界 |
| --- | --- |
| 当前轻量 | pytest **131通过**，0失败/跳过，1条既有httpx弃用警告；2个wrapper内9+12=21个Node项，不额外加到131。其后只改独立浏览器脚本，所有被pytest覆盖的源码字节保持一致。 |
| P2新增 | 旧实现3项先失败；修复后超64KiB取消流/信号、提前read失败中止信号/释放reader、延迟游标429正文与Retry-After均通过。 |
| 新生产构建 | 5个串行构建命令通过；Build ID `XnOBDY6DmSFksnq4CFN-P`；实际Next六类页面303/API401、五类静默SSE撤销、原生HTTP429完整JSON及Retry-After通过。 |
| 新定向浏览器 | 1440/390各3组，共**6组通过**；实际分页HTTP200，response IDs=DOM，跨页无重复；S/A/B、中文搜索、每尺寸10次刷新；pageerror0、网络失败0。最终六卡截图已查看。 |
| 旧完整浏览器 | 59e5286的**15组**完整流程单列保留，包括实际Next退出/引擎继续入库/网站重启查回；不是本次新全量。 |
| 生命周期 | 源码/compiled入口在59e的SIGTERM0、父SIGKILL私有树回收与重启通过；当前入口源码及compiled哈希相同，未重复执行。 |
| 评分预算 | 并发峰值≤2，取消后活动数0；2秒单次与8秒整体超时、一次版本重试均通过。 |
| 重任务 | 唯一主锁覆盖完整进程生命周期，集成优先；最终锁回执exit0。失败批次与修复前日志保留。 |

初次定向浏览器在移动分页等待失败，后一次readiness等待亦失败；保留failure.json/截图。最终测试等待初始化250ms合并刷新、subscriptions/feed请求结束、响应ID与DOM一致后使用cursor，并等最终刷新完成才截图。分页去重断言未放宽，未修改产品controller。最终通过回执明确只有6组。

## 精确绑定与交付文件

- 最终源码62项集合：`695dcbdbc2f169d9e27f6f05679c72029249cdf0f619201e9e201f0965b03dbd`。
- 运行输入349项集合：`98fedb7d612e3fecaf86e1d4db86c81be6b63dc21e32a712e5838c7c706203de`。
- 新构建执行于ff5514c；后续仅integration/tests/feed-browser.test.mjs改变。已逐文件确认349个运行输入不变，并记录当前135个compiled文件；按总管要求不为test-only变化重复构建。
- NIGHT-SOURCE-MANIFEST.json：完整源码hash、依赖固定SHA、SQL/入口/compiled、冻结UI补丁及正式路径映射。
- NIGHT-EVIDENCE.json：当前轻量/生产/定向浏览器、预算、截图、日志及锁回执hash。
- NIGHT-EVIDENCE-59e5286.json / NIGHT-SOURCE-MANIFEST-59e5286.json：前一SHA完整验收基础。
- NIGHT-HANDOFF.md：独立release、配置、init/migrate/preflight/restore与运维命令。

## 运行与剩余边界

由集成按NIGHT-HANDOFF在独立release配置私有job cwd、DATA_ROOT与方向凭据，先显式init/migrate，再preflight；使用B0既有service.mjs tracking start管理compiled入口。Node强制外采关闭，health/ready/status显示source unconfigured，页面显示“未连接真实来源”。本窗口不安装生产job。

正式接线按8b84ee97：候选/api/v1/events/stream映射到/api/v1/tracking/events，controller URL做精确alias，保留Projects全局SSE；共享commands回查保留其他来源。由集成owner在核心冻结后执行。

未验证/未执行：真实6551与QUOTE投递、付费、共享Watch变更、Cloudflare/正式域名及生产新作业、跨Worker最终观察收件。B2 ingest/tracking仍501，outbox为pending或expired_pending_reconciliation，不伪造送达。语音本模块未实现，由UI冻结后接手。
