# B3 feed-query-view-v1 最小只读资源回收补正

状态：pending_chief_review。只改B3自有路径；不新增服务/DB/表/token，不增加8个快照、60秒或64MiB上限。无hint的客户端维持既有协议、配额与429；legacy latest/activities/commands不变。

公开published-v1可显式提供请求头 `X-Tracking-Query-View: qv1_<UUIDv4>`。它只是浏览器每次组件挂载以crypto.randomUUID创建、保存在useRef内的本视图资源标识，不是身份/租户/权限凭据，不用localStorage跨标签复用。BFF严格校验格式，将其作为可选 `query_view_id:string|null` 传既有feed/bases和feed/pages；缺省null。actor仍由当次B1验证，方向token和C03 UDS保持不变；不增加公开query字段或新入口。

basis同一事务先仅删除 `(actor_hash,query_view_id)` 完全匹配的旧bases/snapshots，再做全局容量校验和新basis；非null才触发回收，不影响该用户其他视图、其他用户或scope的查询。刷新/换筛选明确撤销本视图先前查询，旧cursor返回409，已被回收的旧basis返回404；普通翻页不回收，limit变动仍按原ordinal。并发同view初始查询为最新basis优先；controller仍串行合并刷新，并以viewKey忽略旧响应。

仅在004的两张现有短期缓存表加nullable query_view_id列，不改已发布001—003；004尚未冻结。snapshot持有该字段，带hint的cursor在既有签名payload加入w字段；没有hint保留旧cursor形状。Worker检查当前actor与view绑定；BFF不可只凭浏览器自报view撤销别人的资源。签名旧payload无w视作null，旧默认DTO和cursor签名规则保持兼容。回收不续期任何旧snapshot；新查询仍严格≤60秒、basis准备≤15秒，Root已审C03版本/2秒/8秒/并发≤2均不变。

初连历史/legacy activity.created不触发新profile的重复刷新；活跃versioned事件合并250ms后刷新，user主动刷新和连续筛选使用同view hint。验收：同view10次refresh+SSE burst+连续筛选不堆积快照；翻页/limit稳定；两个标签、两个用户互不回收；错误view/cursor422或404；无hint仍第9个活跃查询429；任何失败不吞429、不伪造空结果。已存在两次浏览器失败和network/HTML保留，当前Failed to fetch的HTTP转发还须真实Next复验。
