# 最终上线验收矩阵

每项证据必须绑定同一个最终合并 commit；模块的独立测试、UI原型、进程ready不能替代端到端证据。当前未合并业务分支，下面业务项均是待执行场景。

| 场景 | 操作与必要证据 | 通过条件 |
|---|---|---|
| 登录与账号管理 | 未登录、普通用户、超级管理员；密码错误、限流、退出、禁用、密码重置 | 未登录不能查看业务；普通用户只能读；禁用/重置后旧session失效；认证只存独立auth.db |
| API权限与CSRF | 直接请求BFF/内部API；伪造role/身份header；跨Origin写；过期session；内部错token | 服务端401/403；不接受客户端身份；无权限不能写任何业务库；worker内部接口不暴露到公网 |
| 猎手发现 | 官方方向fixture，5000边界；72小时内A/B关注同一目标；重复事件；单猎手；过期事件 | 正确目标、至少两名不同猎手、只有一条发现；未人工确认不会调用Watch新增监控 |
| 人工加入 | 管理员在正式Next页面操作，记录command_id/event_id/project_id/receipt | tracking持久化任务；重复点击幂等；普通用户403；失败/超时保持pending/unknown并reconcile |
| 远端监控启停 | 独立6551配置，模拟/实测配额不足、失败、断线、重启；操作后回查 | 状态来自远端证据；ACK不等于running；旧共享Watch完全未改变 |
| 推文流转 | 受控NEW_TWEET重复/乱序/重放、断线回补；最终独立账号真实推文 | tracking只有一次业务效果；网站接收回执；主页展示正确项目动态；隐藏Hunter身份与secret |
| 主页与删除 | 查看/修改/评级/进度/搜索；分别删除Hunter、tracking、主页记录 | 数据归属清楚；每次删除后其他两库相关记录和监控状态维持原值 |
| 网站故障 | 原生launchd停止/重启当前测试网站；两个真实worker继续入库；重放到主页 | 两worker PID/连接不因网站重启改变；恢复后无丢失、无重复人工操作/提醒 |
| worker恢复 | 对真实候选worker故障注入，记录前后checkpoint、outbox、远端状态 | launchd重启后恢复持久任务；不从头建立重复Watch、不漏未确认任务 |
| 数据库隔离 | realpath、inode、application_id、DB连接审计、跨库删除前后摘要 | 四库独立；拒绝symlink/hardlink；无ATTACH/跨库读取；只写自己领域 |
| 正式构建与资源 | 同SHA clean构建、固定依赖、Next start；至少30分钟负载与backlog观察 | 无dev/watch；三驻留主进程；无持续swap/backlog增长；延迟/RSS实测记录 |
| Cloudflare与HTTPS | 独立测试域名、TLS、JWT/AUD、WAF/限流、不缓存业务API | 未授权被拦；HTTPS有效；合法登录可用；内部worker端口不可公网访问 |
| 日志与备份 | 脱敏扫描、10MiB轮转触发、夜间任务证据、恢复及业务reconcile | secret不出现；日志有界；备份任务实跑；恢复后任务/业务对账一致 |
| 回滚 | 上一完整release、schema兼容；测试域名切回；保留旧服务 | 可验证恢复到已知版本；不覆盖旧DB/脚本/共享配置；当前数据保持 |

模拟6551场景只证明本地行为；真实NEW_TWEET、平台配额与Watch隔离分别标记“未验证”，直到独立凭证和明确允许的测试范围到位。任何资金交互不属于本次上线验收。
