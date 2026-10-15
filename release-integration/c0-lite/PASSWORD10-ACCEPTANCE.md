# C0-lite 密码下限10增量验收

本地实际生产构建通过。Auth冻结源 `f097bd4722155d5e689b8894956391ed7e5f2fa7` 已以前向merge收入集成分支，审查授权为 `1d56ef2f003c531574e41fe079c70510ac6ed437`。实际运行SHA与升级状态单独记录在忽略目录 `.runtime/c0-lite/deployment.json`、`password10-after.json` 和 `LIVE-ACCEPTANCE.md`；本文件不把构建结果当作公网已部署结果。

正式表单仅改提示与两处minLength，完整SHA256为 `2bbd07de5dc0ee0fa8688d7c30e2e913780cfe67dd907beef671ddda9d07508f`，保留WorkspaceLink和“猎手项目追踪”。77项原受控源中只使用批准的security/CLI两项增量hash，另75项和8项主页文件继续逐字节锁定；原C0规范与历史证据未重写。`verify_password10_intake.py` 同时限制全部接收差异只能是批准9路径、正式表单或release-integration接线/验收文件。

生产构建、typecheck、Auth 68/68、B0 26/26通过。实际Next生产入口使用独立临时库，94项断言通过，包含9字符CLI/API/DOM拒绝、10字符CLI创建及网页改密接受、128上限、原权限、会话撤销、安全固定POST、1440/390布局、项目增改/完成/恢复和备份恢复。另从冻结旧安全代码生成15字符以上口令hash，仅写入隔离合成账号，实际新版HTTP登录通过且hash/version/强制改密位未变；原会话跨实际Next重启继续有效。没有读取、重置或重新验证本人真实口令。

证据：`evidence/password10-summary.json`、`password10-intake.json`、`password10-regression.tap`、`build-attempt-1792080818558.json`、`p0-1792080904960/result.json`及同目录截图。生产BUILD_ID为 `raSoDp37o-uhfiuY_ysZO`，实际源码与编译产物由 `evidence/build-binding.json`绑定。

新增旧会话重启QA首轮在87项通过后因重复进入已打开的httpx客户端上下文失败；仅修测试资源管理，保留 `p0-1792080863806/result.json`，重跑94项通过。

升级只允许既有新站label与新release，沿用 `/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/data`。升级前在线backup到新私密路径，前后比对DB物理路径/inode/schema及全部用户行的聚合指纹；不迁移、不bootstrap、不重建/覆盖库、不改已有用户。保留旧release与plist/environment/owner回滚副本。main、正式域名、旧服务、Watch及其他Tunnel均不在本次变更范围。

公网admin增改/刷新/完成/恢复与持续SSE已在上一运行版本观察通过。公网普通用户仍需实际出现临时账号及只读状态，不能用本地测试或本人“已登录”的回复代替浏览器角色证据；C0-lite最终通过状态须查看最新LIVE-ACCEPTANCE报告。完整猎手链路、三库真实跨域删除、三个监控进程恢复及正式站发布仍未验收。
