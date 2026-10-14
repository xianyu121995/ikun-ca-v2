# 第二阶段服务和数据库归属

版本 `phase2-v1.0.0`。沿用本轮全新 v2 的冻结候选，禁止复制旧版实现/数据库，也禁止为消除接口差异另做一套同功能业务。

## 三个独立服务

| 独立服务和作业 | 受管理进程树 | 数据归属 |
|---|---|---|
| website / ca.ikun.v2.website | Node/Next/Auth；已有 Python Projects 逻辑作为网站受托管私有 IPC 子进程 | auth.db + projects.db，各领域唯一 writer |
| hunter / ca.ikun.v2.hunter | 原入口启动唯一 Hunter 引擎/API，可 execve Python | hunter.db |
| tracking / ca.ikun.v2.tracking | 原入口管理 Python API+engine，统一生命周期 | tracking.db |

只保留这三个可独立启停的服务/launchd作业。Projects 不开放独立 TCP业务端口，不安装独立 launchd，不在网站停止后驻留；使用网站私有 Unix-domain socket/受控本机IPC。父服务检查子进程 readiness、故障与超时，SIGTERM协调退出并回收整个受托管进程树。网站停止时两个 worker 仍独立运行。

这是已有 Python 项目逻辑的运行封装规范，具体 supervisor、IPC与可信身份适配仍由后续放行的 owner 完成，本轮没有实现或启动。禁止再重写项目 CRUD 来替代已冻结代码。网站对子进程的数据访问是 API/IPC，不是跨库 SQL。开发 FastAPI 8120 只用于既有隔离验收，不能直接作为正式第四服务。

Mac IPC socket 目录使用短绝对路径、0700、不可软链接，避免 Documents/TCC 和 Unix socket 路径长度问题；目录内仅所属服务使用。IPC 请求仍带方向凭据/固定scope及经验证身份，不能把“本机连接”当超级管理员。父子必须有绑定的配置与构建 SHA，不继承不需要的 provider/用户秘密。

## 物理数据库

| 库 | DATA_ROOT 内固定路径 | 服务 | 唯一业务 writer | application_id |
|---|---|---|---|---|
| hunter.db | hunter/hunter.db | hunter | hunter-worker | 0x494B0201 |
| tracking.db | tracking/tracking.db | tracking | tracking-worker | 0x494B0202 |
| projects.db | projects/projects.db | website | projects-domain 私有组件 | 0x494B0203 |
| auth.db | auth/auth.db | website | auth-domain | 0x494B0204 |

每 Worktree 独立 DATA_ROOT，禁止软/硬链接、ATTACH、跨库 JOIN、直接读别的 DB/WAL、从旧库导入。一个 writer 的失败只暂停其领域。main 的 foundation SQLite metadata 初始化不等于业务 writer 已正确部署；后续必须使网站 readiness 经项目 IPC 校验，不让 Next 与 Python同时迁移/写同一库。

人类用户、密码/session hash、角色、邀请或登录限流只在 auth.db。业务 DB 可保存自己的 command inbox、来源服务回执、审计 actor_id 与 source checkpoint；不能另建可登录的用户 principals/sessions。候选旧表/凭据属于隔离实验，正式模式须拒绝其作为用户身份；转换需保留数据并经过迁移评审，不能删除库来逃避问题。

## 迁移基线

共同 `_store_identity(singleton,store_name)` 与 `_schema_migrations(version,name,applied_at)` 不改名/改列语义。新校验和放独立 `_migration_checksums(version,sha256)`；版本1基础保留，各库从2独立递增。所有 INSERT 显式列名，不能依赖列数/顺序；候选已有 checksum 扩展列必须有兼容处理和回归，不能直接抛弃数据。

正式 SQL 归 `schemas/<domain>/NNN_name.sql`，每库一个迁移器、一份 source/checksum registry。模块内旧 migration/schema 文件可作为保留候选；正式发布前确定唯一权威位置并校验二者一致，禁止两个启动器重复迁移。变更在显式 migrate/init 或发布步骤执行，不在浏览器请求中自动建库/升级。

WAL、foreign_keys、synchronous=FULL、busy_timeout=5000；文件0600、目录0700。拒绝外来标记/不支持版本/路径别名，不以重建库回退。保留失败现场，恢复到新路径后核对事件/回执。

共同验收必须涵盖新库、foundation→业务升级、已升级库重启、迁移失败回滚/恢复、重复迁移幂等、schema/checksum错拒绝、基础入口与受支持旧二进制兼容。Tracking 四列/基础三值问题是 B0 前置阻断，当前没有修复。

## 配置和生产边界

原 Worktree 端口组与目录保持：website3200/3211/3212，homepage-ui3700/3711/3712，hunter-ui3800/3811/3812，tracking-ui3900/3911/3912，auth3600/3611/3612，projects3500/3511/3512，hunter-worker3300/3311/3312，tracking-worker3400/3411/3412，integration4000/4011/4012。不改其他窗口配置。

外部 I/O、平台写入、付费与资金操作默认关闭；只在独立凭据和明确授权后验真，绝不改共享 Watch。项目主体ID、auth.db以及provider凭据都不从旧版迁移。本轮不安装作业、改Tunnel/域名、合并、生产迁移或发布。

生产仍计划 Node24 LTS、本机原生launchd、串行构建与内存预算；私有IPC子进程也要计入RSS/8GB压力测试。每个业务进程使用独立方向配置，代码 release 与数据库分离，SQLite online backup，不直接cp运行库/WAL。

运行封装依据：[Uvicorn 官方设置](https://uvicorn.dev/settings/)、[Node 24 IPC](https://nodejs.org/download/release/v24.20.0/docs/api/net.html#ipc-support)。部署实现须再按实际锁定版本验证，不能把此规范当上线证据。
