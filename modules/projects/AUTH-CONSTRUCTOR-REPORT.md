# Projects 认证构造器最小修复

夜间放行：`579a57f2e3e470525eb53f9f1f85ba75d25f3728`。本次先独立交付认证修复，不混入 C-03 实现。

`integration/website/lib/projects.ts` 追加只读路径时，改用当前 AuthHttp 实例的 constructor，保留原 store 与错误类所属模块；AuthHttp仅作类型导入。不再用另一 bundle 的 AuthHttp 包装现存 store。B1策略、异常处理、角色、路径白名单和 singleton 标记均不变，没有将未知错误当401或放行。

轻量验证：

- 新 `integration/tests/auth-instance.test.mjs`：3项通过。两个真实编译Auth模块副本的对照中，同模块撤销页面303、错误混搭500；修复后同/跨模块均页面303、API401。额外核对已有页面/Tracking只读路径、Projects精确新只读路径、user写403、admin错误CSRF403、singleton不重复包装及未知错误500。此类身份夹具不打开数据库。
- 真实B1/UDS/导出handler回归：1项pytest通过，内含原10项Node入口测试，不重复累加。覆盖实际页面/Action身份、权限、SSE逐块/静默撤销与取消、命令丢失ACK。只使用临时合成库，没有Next服务或Chromium。
- TypeScript strict/noEmit 单文件检查通过；diff检查通过。认证源码仍取本地冻结Auth `28e6aaf4141790fc74ae4ae4429be4b854460955` 的编译结果，未改Auth源码。密码10增量 `f097bd4722155d5e689b8894956391ed7e5f2fa7` 的真实Next组合由B3按夜间记录复验；这里不声称该组合已通过。

```sh
# Projects Worktree 根目录
/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node --import ./modules/projects/.preview/node_modules/tsx/dist/loader.mjs --test modules/projects/integration/tests/auth-instance.test.mjs
/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/.tools/node/bin/node modules/projects/.preview/node_modules/typescript/bin/tsc --noEmit --strict --skipLibCheck --module esnext --moduleResolution bundler --target es2022 modules/projects/.preview/apps/website/lib/projects.ts
cd modules/projects/candidate
.venv/bin/python -m pytest -q tests/test_b2_browser.py::test_actual_entries_without_proxy --basetemp=/private/tmp/ikun-auth-constructor-entries --junitxml=../artifacts/pytest-auth-constructor.xml
```

真实入口测试前只把修改后的单个自有 helper 复制到忽略预览；旧Next构建不因此变成新构建。未重跑完整Next/浏览器，不占heavy lock，不改其他Worktree/正式apps/root，不启动真实来源，不合并/推送/部署。原B2、协议和失败证据保留。新增测试开发时修正了loader相对路径及B1正则再锚定/null返回值的测试期望；最终3项均通过，不以这些初稿结果冒充业务失败或成功。

具体日志哈希见 [auth-constructor-check.json](integration/evidence/auth-constructor-check.json)。实际Next跨bundle验收仍由B3完成。
