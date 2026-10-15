# ikun.ca v2 模块代码所有权

当前唯一清单：[第二阶段目录规则](phase2/OWNERSHIP.md)和[机器所有权](phase2/ownership.json)。授权必须同时通过[阶段放行](phase2/releases.json)。

全站UI只owns packages/ui；三个页面UI分别owns自己的features/components/prototype。Auth、Projects和两个worker各有对应module/service/schema范围；共享contracts/runtime、root依赖与全站入口由总管持有。任何未列路径、共享依赖、全站接线、schema变更先提审，不能自行扩展。

当前四个UI窗口可以做独立UI；后端和集成新工作held。所有窗口保持原Worktree，不复制其他窗口业务实现、不修改他人代码、不擅自合并或部署。GitHub CODEOWNERS尚未配置真实owner，不宣称远程强制保护已启用。
