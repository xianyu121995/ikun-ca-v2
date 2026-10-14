# 第二阶段请求和展示 DTO

版本 `phase2-v1.0.0`。以下是目标接口，不是已实现能力。API.md 的 envelope、权限、revision、幂等和分页适用于全部 DTO；未知字段拒绝，不透传原始数据库记录。DTO 不含密码/hash/session/provider凭据，Auth写入请求的密码只在内存中处理并脱敏。

## 请求与响应

| API | 请求字段 | data 投影 |
|---|---|---|
| auth/login | username、password | AuthSessionV2；仅Cookie携带session，禁止JSON返回token |
| auth/logout | 空对象 | `{logged_out:true}`，已退出重复调用同结果 |
| auth/password | current_password、new_password | `{changed:true,reauthentication_required:true}`，轮换/撤销旧session |
| auth/users 创建 | username、password、role | AuthUserV2；强制首次改密，用户名唯一，不返回密码 |
| auth/users PATCH | enabled、role、must_change_password 的非空子集 | AuthUserV2；阻止禁用/降级最后一个有效superadmin |
| auth/users/reset-password | new_password | AuthUserV2；强制改密、撤销旧session |
| auth/users 查询 | cursor、limit | PageV2<AuthUserV2> |
| projects 创建 | 完整ProjectFieldsV2 | ProjectRecordV2；home_membership=active |
| projects PATCH | ProjectFieldsV2的非空子集 | ProjectRecordV2，不允许修改只读ID/时间/membership |
| projects DELETE / home-membership | DELETE无body；POST action=add/remove | ProjectRecordV2；已处目标状态无副作用 |
| projects 查询 | API.md查询；rating可用字面unrated过滤null，不把它存入DTO | PageV2<ProjectRecordV2>；默认active |
| hunter/signals 查询 | q、rating、review_state、since/until、cursor、limit | PageV2<HunterDiscoveryV2>；72h合格聚合，阈值沿用候选的≥2不同猎手 |
| hunter/discoveries/{id} | 无body | HunterDiscoveryV2；不返回归因账号 |
| hunter/accounts 创建 | x_handle、label、notes、enabled | HunterAccountV2；仅superadmin |
| hunter/accounts PATCH / DELETE | PATCH为label/notes/enabled非空子集；DELETE无body | PATCH为HunterAccountV2；DELETE `{account_id,removed:true}`，保留审计/历史 |
| hunter/monitoring-requests | confirmed=true、project完整ProjectFieldsV2 | CommandResultV2；discovery信息由服务端读取，客户端不能冒充actor |
| tracking/subscriptions 创建 | project_id、name、x_user_id可null、x_handle、notes、confirmed=true | CommandResultV2（202）；接收命令不等于远端订阅成功 |
| tracking/subscriptions 查询 | q、include_removed、cursor、limit | PageV2<SubscriptionRecordV2> |
| tracking/subscriptions PATCH | name/notes非空子集 | SubscriptionRecordV2；改X目标必须另作明确操作，不能偷换既有身份 |
| tracking/subscriptions DELETE/start/stop/resume | 无body | CommandResultV2（202），路径一律subscription_id |
| tracking/latest 查询 | project_id可选、cursor、limit | PageV2<TrackingActivityV2>，最新received_at降序 |
| tracking/activities 查询 | project_id可选、subscription_id可选、cursor、limit | PageV2<TrackingActivityV2>，发生/接收记录升序；稳定activity_id去重 |
| commands/{command_id} | 无body | CommandResultV2；状态由拥有该命令的worker确认，gateway不猜测成功 |

name/notes沿用项目字段长度限制；x_handle为不含@的1–15字符ASCII字母/数字/下划线，x_user_id为平台十进制字符串或null；平台解析失败保留未知。username规范化策略及密码算法/强度沿用Auth候选，经B1安全回归确认，不由UI校验替代服务器校验。过滤since/until为UTC ISO8601且since≤until；日期控件转时区是纯UI适配。

## 展示类型

- AuthUserV2：user_id、username、role、enabled、must_change_password、revision、created_at、updated_at。所有字段都不包含登录秘密。
- HunterDiscoveryV2：discovery_id（Hunter稳定不透明ID）、project_id（未注册为null）、project（ProjectFieldsV2）、x_user_id、x_handle、profile_bio、followers（未知null）、signal_count（72h去重猎手数量）、first_seen_at/last_seen_at/discovered_at（未知null）、review_state（pending/reviewed/tracking/ignored）、monitoring_state（CommandState或null）、revision。review_state=tracking不代替远端observed_state；UI需展示受理/待核实。
- HunterAccountV2：account_id、x_handle、label、notes、enabled、baseline_ready、connection（unconfigured/connecting/connected/disconnected）、last_signal_at（可null）、revision。connection由实际来源心跳提供；不公开cookie/token/provider地址或账号贡献归因。
- TrackingActivityV2：activity_id（稳定不透明ID）、subscription_id、project_id、project_name、tweet_id（十进制字符串）、x_handle、text（纯文本）、url（安全x.com链接）、occurred_at（未知null）、received_at、source（wss/rest）、generation（正整数）。同(subscription_id,generation,tweet_id)幂等；发生时间未知按接收时间展示并标明。
- PageV2<T>：items为T数组、next_cursor为字符串或null。cursor必须绑定scope、过滤与排序，不允许把另一个查询cursor当成当前查询结果。
- CommandResultV2的project_id/subscription_id在人工确认尚待canonical解析时可null，不能生成demo ID占位；Tracking执行命令的project_id始终为canonical。人工确认后沿用同一个command_id贯穿outbox、回执和Tracking执行。

SSE仅发布脱敏公开投影，使用标准envelope的request_id和事件id/类型：project.updated、hunter.discovery.updated、tracking.subscription.updated、tracking.activity.created、command.updated。data为对应DTO；scope和角色重验，id稳定支持Last-Event-ID。内部hunter.monitoring_requested等不能原样传给浏览器。

已有候选差异（例如target/handle、grade/score、version、epoch、project_id代订阅ID、latest无cursor）由对应领域批次做最小映射。UI0只实现纯投影与回调；缺字段null/不可用，不假造远端状态，也不自行生成canonical/subscription ID。
