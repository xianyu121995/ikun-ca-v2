# 环境检查 · 2026-10-15

已在本机只读核实：Mac14,3 / Apple M2 / arm64，物理内存 8589934592 bytes（8GiB），macOS 26.4.1，当前卷可用约 98GiB。

| 工具 | 本机已有 | v2 使用 |
|---|---|---|
| Git | 2.54.0 | 新独立仓库、本地提交与 Worktree |
| Node | 全局 25.9.0 | 项目忽略目录中独立 Node 24.22.0 |
| npm | 11.12.1 | 只读 npm metadata 查询 |
| pnpm | 10.33.1 | workspace 与 committed lockfile |
| Python | /usr/bin/python3 3.9.6 | 本基础工程不依赖 Python；业务候选自行隔离工具链 |
| GitHub CLI | 未发现 gh | 私有 remote 只规划，owner 待填写 |

Node 来自官方 `node-v24.22.0-darwin-arm64.tar.gz`，SHA256：
`6a9724d9b50a5f22b4816cded441b5a8d9ddae546191a5e5b7efa5a5e2ee26d5`。
下载前读官方 SHASUMS256.txt，解压前比对一致。没有更换全局 Node。pnpm install 下载新依赖并生成锁文件；Next 16.4.1 / React 19.3.1 / TypeScript 5.9.3。

首次 sandbox 的 npm DNS 和 loopback listen 被限制；只对依赖下载和本 v2 临时集成测试申请执行权限后成功。没有自动审批拒绝，没有依赖旧版 node_modules、数据库或配置。

检查发现机器上已有 Python/PostgreSQL/cloudflared 等进程；只读查看型号、进程名称和监听端口，没有停止/重启/修改这些服务。并行窗口在新主目录写入业务候选，基础提交采用文件白名单，不包含它们，也不覆盖它们。

原生生产路径计划放在 `~/Library/Application Support/ikun-ca-v2`，避免生产依赖 Documents 开发路径。真实 launchd 作业、域名、认证、采集恢复均不属于本次验证。

参考：[Next.js 官方安装要求](https://nextjs.org/docs/app/getting-started/installation)、[Node.js 官方发布](https://nodejs.org/en/about/previous-releases)、[GitHub CLI 私有仓库创建](https://cli.github.com/manual/gh_repo_create)。
