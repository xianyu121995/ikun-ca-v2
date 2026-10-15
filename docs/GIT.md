> 第二阶段权威规范：docs/phase2/README.md；本轮所有合并/推送/生产动作暂停。

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

初始架构提交 f89d8f5；9个已有v2候选现已各自在原Worktree冻结，完整SHA见 docs/phase2/source-freeze.json。分支只能由一个Worktree checkout。

当前第二阶段禁止 merge、cherry-pick、rebase、reset/amend 冻结提交、push与部署。总管此次仅在main提交统一规范，不合并业务候选；codex/develop保持原基础提交。各窗口只读主仓库规范或 git show phase2-spec-v1.0.0:docs/phase2/README.md，不擅自把规范提交整合到自己的分支。

未来获授权的集成才执行：收件SHA/验收/文件白名单 → 独立候选组合 → 全部门禁 → 再审发布。当前 stages/held 不构成这项授权。不得force push、删除/重置其他窗口Worktree。旧 homepage-projects 未出生分支保留，不作为合并源。

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
