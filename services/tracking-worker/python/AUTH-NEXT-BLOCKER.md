# B3 本地 Next 认证阻断

状态：**BLOCKED，不能签为全站 AUTH-01/03 通过。** 验证范围是本模块私有 Next 生产构建预览、临时账号和 owner 管理的临时库，没有访问实际用户库或域名。

## 实际现象

固定 B1 `28e6aaf4141790fc74ae4ae4429be4b854460955`、B2 `d0fdefab2aa230ebb8df856aed306d0184d362e2` 的组合中，先登录并经过 Projects/Tracking 业务路由，再用固定 B1 LocalAccounts API 禁用临时普通用户：

- 重新加载 `/tracking` 返回500 `INTERNAL_ERROR`，没有303跳转登录。
- 相同旧Cookie调用 Tracking查询API也返回500，预期401。
- 随后的无Cookie业务页面请求同样可返回500；登录页自身和合法登录、普通用户业务写入403仍能工作。
- 失败响应只有error/request_id，没有业务data，页面不再包含live业务内容；这是必须修复的认证集成错误，不当作成功验收。

实际截图、请求编号和具体次数见最终 `B3-EVIDENCE.json` 的 browser receipt；过程失败现场保留在 `artifacts/b3/browser-1792080819105/`、`browser-1792081377131/`。

## 已完成的本模块修复

Tracking不再构建或替换全局AuthHttp。使用冻结 `/api/v1/events/stream` 入口与B1既有只读规则，候选仅代理Tracking事件；统一多来源网关仍由集成owner组合。新增实际入口回归确认Tracking调用前后B1 singleton不变。89项轻量回归通过（含1个wrapper中的7项Node检查）。最终327个固定/覆盖文件核验一致的Next组合中仍重现5次500；browser-1792083074052已完成两种尺寸，其跟踪流程通过、整体PARTIAL，具体request_id见receipt。

Auth和Projects源文件完全保留固定Git字节，没有在预览中偷偷打补丁。

## 定位依据与推断

固定B2 `modules/projects/integration/website/lib/projects.ts` 的projectsAuth会用本构建中的 `new AuthHttp(current.store, ...)` 替换全局对象，同时复用已有store。B1错误处理通过 `instanceof AuthError` 识别401。若Next不同bundle里的AuthHttp和已有store引用不同AuthError构造器，原401会被归为未知错误500。

独立Node双模块副本实验已执行，结果保存在 `artifacts/b3/auth-class-diagnostic.json`，没有打开任何Auth数据库：

| 组合 | 实际页面拒绝状态 |
|---|---|
| 同模块Http + store抛出的AuthError | 303 |
| 不同模块副本Http + 原store错误 | 500 |
| 保留原实例构造器 + 原store错误 | 303 |

这证明该组合会产生所见错误；对Next现场具体构造器归属仍是基于代码与实验的推断，不能代替修复后的真实Next复验。

## 供owner审阅的修复方向（未应用）

优先由B1提供同实例的追加路由策略入口；或由B2在重建时保留原实例的构造器，避免把另一个bundle的Http拼到旧store上。例如B2现有projectsAuth中的重建可审阅为：

```ts
const CurrentAuthHttp = current.constructor as typeof AuthHttp;
globalState.ikunAuth = new CurrentAuthHttp(
  current.store, [...current.readApi, ...readPaths], current.readPages,
);
```

上面方向仅在独立Node对象组合实验中验证，**未应用到冻结B2或真实Next**。需B1/B2 owner前向修复并由总管冻结新依赖，再复验：匿名页面、禁用/退出/改密/7天过期旧Cookie、API401、页面303、静默SSE撤销，以及Projects与Tracking路由交替访问。禁止把500改为允许访问、伪造会话或放宽权限。

## 已知Auth增量

批准的密码下限10增量为 `f097bd4722155d5e689b8894956391ed7e5f2fa7`；审查记录固定于 `1d56ef2f003c531574e41fe079c70510ac6ed437:docs/c0-lite/password10-review.json`。已读取该记录，三处runtime变更仅长度/提示，API/schema/会话协议不变。本B3继续明确使用原固定B1基线，增量由集成owner更新；不修改旧冻结清单，也不把该增量当成本问题已修复的证据。
