# ikun.ca v2 所有窗口开发规则

当前规范：phase2-v1.0.0。优先读取 docs/phase2/README.md、API.md、STORAGE.md、UI.md、OWNERSHIP.md、RELEASES.md 与机器清单；第二阶段规范取代基础阶段中已过期的角色、删除、进程与目录描述。当前用户禁止重复开发、擅自合并和生产部署。

## 开工前

- 在自己的原 Worktree 明确设置命令 cwd，核实 Git top-level、codex/<module> 分支与 source-freeze 的提交；聊天默认 cwd 仍可能是上层目录。
- 目录所有权和阶段放行同时满足才可修改；UI0仅四个UI窗口，其余新功能工作 held。完成前置不自动产生后续许可。
- 本轮不 merge/cherry-pick/rebase/reset/amend 冻结提交、push 或部署；主目录是总管工作区，不整体 git add，不覆盖/清理其他窗口候选。

## 模块和数据

- 全站UI设计 owns packages/ui；三个UI窗口各自拥有自己的页面/feature/prototype路径，只做展示与回调，不实现业务。
- 登录系统 owns modules/auth/schemas/auth；项目管理 owns modules/projects/schemas/projects；两个worker只改对应service/schema。全部精确范围见 ownership.json。
- 总管持有 root配置、锁、contracts/runtime、全站layout/globals/rootpage/proxy/通用gateway；此轮只提交规范、类型和校验，不代写业务、不合并其他候选。
- 三个独立服务/launchd作业：网站（Auth与受托管Projects私有IPC组件）、Hunter、Tracking。沿用本轮已有v2成果，不开发第二套CRUD/引擎；旧版代码/库/账号绝不复用。
- 四库物理隔离、一个领域唯一writer；禁止ATTACH/跨库SQL/直接读别库DB/WAL。用户/密码/session/角色凭据只存auth.db。主页移除不自动暂停/删除监控；监控移除不改主页。
- 固定scope ikun-main；人类仅superadmin/user，user业务只读。服务身份方向隔离；权限由服务器验证，不信客户端头或展示按钮状态。
- Hunter个体身份、raw payload和secrets不得进入普通DTO、历史、SSE或日志。密码表单必须显式同源POST，脚本失效不能GET提交。

## 工程和交付

- 遵循现有TypeScript/Python实现，最小适配；timeout/backoff/rate-limit、幂等、revision、checkpoint、outbox/inbox、未知结果reconcile、优雅退出按冻结规范。禁止伪造通过、连接或任务完成。
- Node24.22与冻结依赖，各Worktree独立.env/依赖/var/端口；8GB机器构建串行。根依赖/锁文件只有总管可改。
- DB、WAL、密钥、Cookie、运行数据均不入Git；本地配置0600，不在聊天/日志传secrets。原hook正常执行；仅白名单暂存自己的文件。
- 每交付给出完整SHA、规范版本、文件范围、命令结果、未验证项和剩余阻断。冻结不等于验收；失败报告原样保留。
- 旧服务、共享Watch、Cloudflare Tunnel、生产数据和域名均为禁止修改边界。真实平台/付费/资金动作另需用户授权，Web3默认dry-run。所有源版本和部署审批绑定具体SHA。
