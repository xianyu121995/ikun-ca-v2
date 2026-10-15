# B1 最终版集成交接

用户最后确认的需求优先于冻结 phase2-v1.0.0 的账号管理协议；本候选不改共享 contracts/API/lock，下面是供总管收件时同步的明确差异。原 `48d9dd4` 只作旧方案证据，不再是最终需求的 PASS 依据。

## 外部接口

统一 JSON：成功 `{data,request_id}`；错误 `{error:{code,message,retryable},request_id}`，带 X-Request-ID 和 no-store。所有写入 JSON + 同源 Origin，已登录写入额外 `X-CSRF-Token`。Host 必须匹配固定 Origin。

| 接口 | 输入 | 输出/行为 |
|---|---|---|
| POST /api/v1/auth/login | username,password | AuthSession 投影+CSRF；设置随机会话 Cookie，强制改密状态仍有效 |
| GET /api/v1/auth/me | Cookie | user_id,username,role,tenant_id,must_change_password,csrf_token,capabilities |
| POST /api/v1/auth/logout | {} | `{logged_out:true}`；撤销当前会话/清 Cookie；重复退出安全 |
| POST /api/v1/auth/password | current_password,new_password | `{changed:true,reauthentication_required:false}`；撤销所有旧会话并设置全新 Cookie，随后重新 GET me 获取新 CSRF |
| GET /api/auth/session | Cookie | 暂留跟踪兼容 `{user:{id,username,role,must_change_password},csrf_token}`；同样实时校验，不是新的管理 API |

`capabilities.can_manage_users` 恒 false（仅保留兼容字段）；其他业务能力只有完成改密的 superadmin 为 true。user 和强制改密用户不可凭前端能力字段授权。旧 users/list/create/PATCH/reset-password 全部移除，404；无公开注册/删除/角色修改/本地管理代理 API。

**与旧 B1 的必要变化**：会话12小时改为7天绝对上限；bootstrap 必须首次改密；本人改密从清 Cookie/重新登录改为原子撤销旧会话并设新 Cookie；旧网页管理 DTO/幂等键协议不再适用。原持久表/历史回执保留，不为移除 API 删除表或改写 schema002。

## 实际服务端入口

编译 `modules/auth/tsconfig.json` 后导入 `modules/auth/dist/src/server.js`：

- `getSession(request)`：实时验证本人会话，返回安全投影；允许强制改密会话获取本人的状态，**不能把 getter 当业务鉴权**。
- `requireIdentity(request)`：业务页面/API 权限检查，返回冻结的 `{user_id,tenant_id:'ikun-main',role}`；强制改密拒绝；user 只读路径必须在认证适配器白名单中。
- `requireSuperadmin(request)`：在实际业务执行前验证身份、强制改密、角色及写入 CSRF；普通用户即使对 GET 入口也拒绝。
- `withAuth(request,handler)`：调用 handler 前重新验证，并返回统一401/403/503等错误；自动包装 SSE 持续撤销。handler 内仍负责资源归属、输入、revision、幂等和业务事务。

Route Handler 示例（路径按接收文件位置调整）：

```ts
import { withAuth } from '<relative>/modules/auth/dist/src/server.js';
export const runtime='nodejs';
export const dynamic='force-dynamic';
export const POST=(request:Request)=>withAuth(request,async principal=>{
  // 此处已经校验完成改密的 superadmin；下一步执行该领域自己的业务函数。
  return projectDomainWrite(request,principal);
});
```

不得缓存会话、principal 或认证结果，不得采纳客户端 x-role/x-user。固定 `ikun-main`，跨scope query/header拒绝。未知读API默认不给普通用户；各owner只将已审核且无副作用的GET加入 `src/server.ts` 清单。

`integration/website/lib/auth.ts` 提供 Next Server Component `requireAuthPage(path)`，在**每个实际受保护页面**执行，不仅放在共享 layout。401重定向登录，强制改密重定向改密页，其他异常拒绝；路由渲染 force-dynamic。

Server Action 必须在函数体内调用 `requireSuperadminAction(csrfToken)`：

```ts
'use server';
import {requireSuperadminAction} from '<relative>/lib/auth';
export async function updateProject(form:FormData){
  const actor=await requireSuperadminAction(String(form.get('csrf_token')??''));
  return projectDomainWriteAction(form,actor);
}
```

表单从已验证的服务端会话安全投影取 CSRF，放 hidden 字段（不得放URL）。辅助函数在当前请求读取 Next headers，校验原始 Host/Origin/Cookie/form CSRF，按业务写入验证 superadmin。底层 `AuthHttp.serverAction` 亦可用于其他 Next 适配。不要将读取接口的身份获取结果替代本函数。测试在 `/internal/v1/` 的 Proxy 排除路径调用真实 Route Handler/Server Action，证明不是只靠 Proxy。

## UI 收件范围

只接 `integration/website/**` 的认证路由、`components/auth/**` 和 `lib/auth.ts`，**proxy 是候选，须与主站已有 proxy 合并审阅，不可整份盲覆盖**。移除旧 `/login/route.ts`、`/auth/[[...path]]/route.ts`、static assets 接线，避免 page/route 冲突和旧管理后台残留。

实际页面使用公共 `LoginPanel`、改密 Input/Button/Panel、Alert 与 AppShell。`AuthShell` 不给公共 AppShell 传 account 参数，侧栏只有三个业务导航；右上 details 用户菜单只有用户名、修改本人密码、退出。业务 owner 组合此 shell 或复用该菜单，不加管理入口。页面导入 `@ikun/ui/styles.css`，固定公共 UI 不另改。

## 构建/存储/配置

总管在主站构建前编译认证模块，并为网站接收现有 `@ikun/ui` workspace 依赖（根依赖/锁仍由总管处理）。Auth 运行在 Next Node24.22，无独立服务、Python运行时、第三方认证依赖或部署脚本。

唯一DB `DATA_ROOT/auth/auth.db`；显式 migrate/bootstrap，运行时/health 不DDL。auth schema2 admission 需要领域checksum/scope验证；B0 默认maximumVersion1不全局放宽。`integration/preview-only/lib/stores.ts` 只打开auth，是验收夹具，不能直接替换真实多域/IPC readiness。其他领域不得读此DB，应调用统一认证函数；worker 信任与业务回执由总管另行集成。

`integration/preview-only/**` 全是测试夹具，包含虚构业务页/API/Server Action，通过结果不代表真实项目/监控已开发。不得作为正式接口部署。交付只提交认证候选，不合并、不push、不部署，不修改线上、旧库或监控。

Server Component/Action 接线参考已核对的 [Next.js Authentication](https://nextjs.org/docs/app/guides/authentication) 与 [Proxy](https://nextjs.org/docs/app/api-reference/file-conventions/proxy) 官方文档：Proxy 只是入口预检，实际操作仍由请求内的鉴权函数执行。

auth 备份请使用 SQLite online backup 或停网站后完整备份（不可遗漏 WAL）。回滚仅恢复 auth 的受审阅备份并回退认证版本，不回滚业务库；恢复旧 auth 备份可能失效备份之后的会话，需重新登录。既有账号不做静默删除/角色变更；如收件环境已含旧方案的多个管理员，由总管另审本机处理方案，不自动降级账号。
