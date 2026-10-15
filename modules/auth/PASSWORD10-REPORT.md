# B1 密码最小长度10：增量交付

基线 `28e6aaf4141790fc74ae4ae4429be4b854460955`，原Auth Worktree/`codex/auth`前向修订，不reset/amend，不重复开发。范围只将新设/修改/CLI重置或恢复的最小密码长度15降为10，并同步提示与测试。规范增补为本模块 `AUTH-CONTRACT-password10.md`，继承主仓库 `docs/b1/AUTH-CONTRACT-v2.md`；读取时主仓库HEAD `63e8a2857241c6a76226f21435e40db9736a1e7e`，规范文件SHA256 `b50887f551550f8754987cbbdded3bcc485ba7ded799baf046f0237c61258589`。

## 范围

- `src/security.ts`：创建/新密码下限及对应提示15→10。登录验证仍按原1字符下限读取已有密码，上限128 Unicode码点/512 UTF-8字节不变。
- `integration/website/components/auth/forms.tsx`：新密码及确认新密码 minLength=10，说明文字同步。原密码字段和固定同源POST不变。
- `src/cli.ts`：初始化/创建/重置/恢复共用隐藏输入提示改为至少10字符；命令和TTY/双输逻辑未改。
- `README.md`、`INTEGRATION.md`：只补充密码政策；原报告、原合同与全局冻结规范不回写。
- 新增 `tests/password10.test.mjs` 14项，增强 `tests/browser_smoke.py` 的10位输入、9位拒绝和DOM约束验收。原54项Node测试源文件及helper均原样保留。

Argon2id及并发、CSRF、Cookie、限流、7天绝对会话、改密撤销/轮换、角色/单有效超管、首次改密、schema及存储均不变。不增加网页账号管理/重置接口。不迁移、不重写任何现有DB/hash，不要求现有用户再次改密，不接触已上线用户密码。

## 自动化

`pnpm exec tsc -p modules/auth/tsconfig.json`通过。

`node --test --test-concurrency=1 modules/auth/tests/*.test.mjs`：**原54项 + 新增14项 = 68/68通过**，失败/跳过/取消均0，约55.8秒。新增覆盖：

1. ASCII9拒绝、10接受、128接受、129拒绝（4项）。
2. Unicode9/10码点，以及128 emoji=512字节接受、追加一ASCII=129码点/513字节拒绝（4项）。有效Unicode每码点最多4字节，128码点内不会超过512字节；不伪称构造了“128码点且513字节”。
3. 登录原1字符校验保留（1项）。
4. 本地bootstrap/create、本人改密API、local reset-password、local recover-admin共用9拒绝/10接受（4项）。
5. 用冻结28e6aaf的原始security源码生成15+旧hash，在合成临时库验证原密码登录、重启、hash/version/must_change_password不变（1项）。

原54项安全/会话/撤销/权限/存储/迁移回归均重新执行，不引用旧成绩代替。新日志仅为 `test-results/password10/regression.log`。

## Next/Chromium 与重任务锁

完整构建及浏览器使用总管共享锁，原脚本SHA256 `2c4775d7ac0b96b8b84c9c88489c63ba116d9773e1c2b6b5fe5f12848e04c848`：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py \
  --owner chief-review --timeout 600 -- python3 modules/auth/test-results/password10/run-heavy.py
```

**Next.js完整生产构建及Chromium验收均通过，page errors=0，业务库创建数=0。** 前台命令串行执行prepare-preview、build-preview、真实Chromium验收。只使用合成账号和临时auth.db；没有访问任何v2现有用户、业务库、监控或生产服务。锁回执为主仓库 `var/coordination/chief-review-aff010f3-ee2e-4f4b-9fd2-c7a9170aa2f4.json`。新构建/浏览器JSON与日志、截图副本均独立存放 `test-results/password10/`（浏览器控制台输出为`browser-run.log`，截图为`browser/`）。重任务结果、源码hash、锁receipt位置和完整最终SHA在本地ignored `test-results/password10/receipt.json`，本报告不会写入自身Commit造成自引用。

收到总管后续收口指令前，本轮已获锁并完成上述隔离构建/浏览器，故不将已运行检查改写为“未启动”。**实际C0-lite网站构建/浏览器与upgrade未启动，移交集成窗口集中验收；不再重复隔离重任务。** 最后追加轻量静态核对两字段minLength/maxLength及公共登录/改密固定同源POST，结果为static-check.json。

浏览器检查两处minLength=10/maxLength=128、9位浏览器约束、10位真实首次/主动改密、PTY bootstrap/create/reset/recover的9拒绝及10接受；复验7项CLI、权限/会话及原4组无JS/chunks阻断密码表单固定同源POST且无URL/历史/响应/日志泄密。桌面1440×1000、手机390×844。

旧脚本固定输出位置：执行前按原字节备份至 `password10/baseline28/`；执行后新结果独立归档至 `password10/`，恢复旧根路径并核对SHA256。`frozen-evidence.json`记录before/after；旧报告、54项回执和冻结证据均保留。旧 `scripts/final-receipt.mjs` 仍属于原54项方案，不用它冒充本次68项的新回执。

## 边界与未验证

仅本地Auth增量候选，需总管审查具体新SHA。没有合并/推送/部署；不执行upgrade_c0_lite.py，不修改测试站或线上服务。公网/Cloudflare/真实业务集成、真实账号密码和生产数据均未验证也未触碰。本轮旧证据保持原状态；最终构建/浏览器结果以本次独立receipt为准。
