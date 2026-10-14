# 单仓库、分支与私有 GitHub 规划

主仓库为 `ikun.ca开发/ikun-ca-v2`，是新建独立 `.git`，与上层空仓库和旧版仓库无共享历史。开发 Worktree 在同级 `ikun-ca-v2-worktrees`，只有一个 common Git directory，不是三个子仓库。

| 分支 | 目录/作用 |
|---|---|
| main | 主目录，经过验收的基础/发布基线 |
| codex/develop | 集成分支，开发窗口从此基线出发 |
| codex/website | ikun-ca-v2-worktrees/website |
| codex/hunter-worker | ikun-ca-v2-worktrees/hunter-worker |
| codex/tracking-worker | ikun-ca-v2-worktrees/tracking-worker |
| codex/projects | ikun-ca-v2-worktrees/projects |
| codex/auth | ikun-ca-v2-worktrees/auth |
| codex/homepage-ui | ikun-ca-v2-worktrees/homepage-ui |
| codex/hunter-ui | ikun-ca-v2-worktrees/hunter-ui |
| codex/tracking-ui | ikun-ca-v2-worktrees/tracking-ui |
| codex/integration | ikun-ca-v2-worktrees/integration |

初始架构提交在 main，随后创建 develop 和独立窗口 Worktree。分支只能由一个 Worktree checkout。后续专题分支使用 `codex/<module>-<task>`。先提交基础架构再交接，窗口业务尚未开发。

合并步骤：窗口自测、提交、交付 SHA → 总管审阅范围/接口/隐私/兼容 → 合并 codex/develop → 串行 build/typecheck/test/smoke → 验收后 main/tag。不得 force push 主分支；不要删除/重置其他窗口 Worktree。冲突只由相关 owner 协调；main 更新后窗口自行合并或 rebase 自己的未共享工作。

## 私有远程（规划，未创建、未推送）

远程名 origin，建议仓库 `<确认的 GitHub 用户或组织>/ikun-ca-v2`，必须 private。不猜 GitHub owner，不采用旧版 remote，不使用旧仓库。当前 gh 未安装且 owner 未提供，因此基础工作只提交本地。

可在忽略的 `config/github.local.json` 填写 owner；不填凭据。owner 确认并完成本机认证后，可在新仓库根目录执行下列命令（文档不构成已执行记录）：

```sh
gh auth status
gh repo create CONFIRMED_OWNER/ikun-ca-v2 --private --source=. --remote=origin
git push -u origin main
git push -u origin codex/develop
```

不要把占位 owner 原样执行。创建后用 `gh repo view --json nameWithOwner,visibility` 验证 PRIVATE，再配置 CODEOWNERS 和保护规则。不要将 GitHub token 放仓库/聊天；gh/macOS Keychain 或 SSH agent 处理认证。

仓库启用 `core.hooksPath=.githooks`，pre-commit 做跟踪路径与常见密钥格式检查；`.gitignore` 覆盖 DB/WAL、secrets、运行数据。检查器是辅助 guard，不能识别所有密钥；禁止 `git add -f` 敏感文件。Worktree 会继承 shared config，但新 clone 需要再次设置 hooksPath。

未配置用户 Git 身份时，初始提交使用仓库局部技术身份 `ikun-ca-v2 Architecture <architecture@ikun-ca-v2.invalid>`，不会改全局配置。后续窗口应设置自己的真实提交身份。
