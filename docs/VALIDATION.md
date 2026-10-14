# 基础架构验收 · 2026-10-15

范围仅是新的三个服务工程骨架。可定位基线为 Git tag `foundation-v0.1.0`，完整 SHA 用 `git rev-parse foundation-v0.1.0` 查询。本文件随基础提交保存，不把业务候选/生产/fixture 结果混在一起。

| 检查 | 结果/证据 |
|---|---|
| 官方 Node LTS 下载哈希 | 匹配，见 ENVIRONMENT.md |
| pnpm install | 6 workspace projects，lockfile 已生成 |
| pnpm build | contracts、runtime、两个 worker、Next.js 全部成功；Next cpus=1 |
| pnpm typecheck | 5 个模块全部通过 |
| pnpm test | 5 passed，0 failed |
| pnpm smoke | 3 个独立生产模式服务 + 4 库 + API 鉴权 + worker 各自停止/重启 + 全部退出，通过 |
| launchd plist 生成 | 三份生成，plutil -lint 均 OK；没有安装 |
| git ignore | env、DB、WAL、私钥、运行目录忽略；contracts/runtime 源码和锁文件可提交 |
| pre-commit/check:git | 对 Git index 路径与常见密钥格式检查，在提交时执行 |

5 个测试覆盖：服务存储所有权/不同 inode/重复迁移；外来库拒绝并保留标记；软/硬链接拒绝；服务 token fail closed；项目 ID 与 request ID 校验。测试文件仅在 `/private/tmp` 创建本 v2 临时 SQLite。

smoke 使用临时端口与临时数据，启动 compiled workers 和 `next start`。网站首页 200；公开业务 API 503；内部缺 token 401、有效 token 后未实现业务 501、status 200；停止 hunter 后网站/tracking 仍 ready；停止 tracking 后网站/hunter 仍 ready；重启读取原临时库。测试结束服务停止、临时数据清理。它不证明真实采集、登录或业务 CRUD。

修复过的验证差异：Next 16.4.1 源码明确在 SIGTERM cleanup 后退出 143，smoke 最初错误要求网站退出 0。已按已安装框架源码校验网站 0/143、workers 0，并把成功消息移到所有清理通过之后。最终 smoke exit 0。

未执行：旧版代码/DB 复用、Watch 修改、生产数据库迁移、安装 launchd、Tunnel/域名改动、GitHub 创建/推送、真实登录、业务 CRUD/采集、真实付费/资金调用、页面浏览器交互验收。

并行窗口候选目录保留未纳入本次基线；主目录因此可能有 untracked 文件。不能把未跟踪的其他窗口候选当作架构脏改动删除，也不宣称整个主目录 clean。独立 Worktree 的基础 checkout 才是清晰的开发起点。
