# B4 接线候选

所有文件是 Hunter 自有目录里的待审候选，没有写入正式网站或其他 Worktree。固定来源与状态见上层 B4-REPORT.md 和 docs/b4/receipt.json。

`website/lib/hunter.ts` 在每次实际 Route Handler 内调用 B1 withAuth/requireIdentity/requireSuperadmin；页面内 requireAuthPage，Action 内 requireSuperadminAction。只转发自己构造的方向凭据、刚验证 principal、合法业务版本/幂等头，丢弃浏览器 Cookie/Authorization/伪造角色/actor头。Hunter服务不持有人类 session。SSE贡献重验建连/数据块/静默撤销、取消上游；多来源统一游标及最终根gateway仍归C0，不用本候选覆盖Projects入口。

controller只使用真实同源API，不导入seed或回退演示。GET筛选/游标在服务端执行；定稿内部10条翻页在当前最多100条服务器页内，姓名/评分/信号排序只对当前服务器页，不冒称全量排序。未知粉丝/时间/统计保持未知；管理员名单不呈现，管理按输入 handle 操作必要账号 DTO。user只读。确认超时保留原UUID并锁定后续盲写；人工202仅显示待核实。没有冻结的Hunter操作回执查询公开路由，不临时发明接口；原确认ID尚未返回时需由受控接收链/总管核对，不自动换key重试。

补丁仅修改固定 Hunter UI `08065d7` 的 App.tsx/model.ts，绑定props/callback、角色、错误/unknown/分页与字段限制，不改CSS或公共组件。研究独立保存C-04禁用；原始bio/未冻结的代币计划与持续关注标记只读。人工确认保留完整DTO中未展示的赛道/进度/日期字段，不把原型token枚举当正式字段。定稿v3本身只有项目资料页，不新增其他面板或设计。

在本模块 python 目录，轻量复现（现有独立依赖，无安装）：

```sh
.venv/bin/python -m pytest -q --junitxml=docs/b4/python.xml
node integration/tests/prepare-light.mjs
node --test integration/tests/guards.test.mjs
.venv/bin/python integration/prepare-ui-patch.py
node integration/tests/typecheck-light.mjs
```

`node` 使用已冻结 Node24 工具链。prepare-light/typecheck-light 只从固定Git对象读取依赖到自己忽略的var，不修改或运行其他窗口。没有full build/install/browser。

正式本地服务必须先显式迁移，再serve（本轮尚未启动此服务）：

```sh
# 在自己的本地配置填入独立方向token；不在聊天中传递。默认真实来源与任务投递关闭。
HUNTER_V2_MODE=1 HUNTER_DB=./var/formal/hunter/hunter.db .venv/bin/python -m hunterradar init
HUNTER_V2_MODE=1 HUNTER_DB=./var/formal/hunter/hunter.db .venv/bin/python -m hunterradar run
```

未配置方向token时业务返回503，ready不代表真实来源连接。正式Node选择原 `HUNTER_ENGINE=python` execve入口；DATA_ROOT路径仍为 hunter/hunter.db。不安装LaunchAgent、不动旧服务。

后续重任务须先等总管解除优先时段，再用唯一共用锁包住整个前台生命周期，例如（当前未执行）：

```sh
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- .venv/bin/python scripts/process_smoke_b4.py
python3 /Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2/scripts/with-heavy-lock.py --owner hunter-worker --timeout 600 -- .venv/bin/python integration/build-preview.py
```

完整预览装配/构建脚本已写但未执行；只从固定Git导出，offline安装、串行build，不加载现有服务配置。浏览器验收仍待补齐实际运行证据，不把上述脚本存在写成构建或验收成功。
