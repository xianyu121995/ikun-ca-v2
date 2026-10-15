# 独立 Tracking venv 部署预检增量

基线为已冻结B3交付 f3bc19503ae33e000bdd33c140baa1fe77c9109a（业务源码c4de379a67bd9b154bab87ce81d4645b53102ea0，root冻结d0af2804ed1ad70d3dd66e930582831bbd6b5e96）。本次仅preflight-release.py、test_preflight.py及本文档三文件前向增量，不改Worker、SQL、入口、依赖锁、网站或旧回执。

## 变更与运行

新增可选绝对参数--venv-root。指定时必须严格等于release.parent.parent/venvs/tracking，且实际sys.prefix的绝对值/resolve值相同；owned root、venvs、tracking须当前用户持有且无group/other权限。路径各级拒绝软链接及相对、点段、..、尾斜杠等别名。缺参保持旧release内venv兼容。

正常venv/bin/python可以链接到受管理base interpreter，不要求其realpath位于venv内；解释器执行文件hash仍由70f6c2b部署guard验证。预检自身及Tracking config/migration导入来自指定release；entry和requirements实际字节必须匹配冻结manifest的固定hash，全部25个pinned依赖逐项用本地importlib.metadata核对已安装版本，不联网安装。

保留私有config/job cwd、无.env、独立方向凭据、外采关闭和tracking.db身份/迁移校验。关闭pycache写入；预检不init/migrate、不执行DDL、不启动服务、不访问provider。

```sh
/ABS_OWNED_ROOT/venvs/tracking/bin/python -I -B /ABS_OWNED_ROOT/releases/RELEASE_SHA/services/tracking-worker/python/integration/preflight-release.py --release-root /ABS_OWNED_ROOT/releases/RELEASE_SHA --job-cwd /ABS_OWNED_ROOT/jobs/tracking --config /ABS_OWNED_ROOT/config/tracking.json --venv-root /ABS_OWNED_ROOT/venvs/tracking
```

集成须按增量更新发布计划中的preflight文件hash；旧NIGHT manifest与验收记录保持冻结，不用其旧preflight hash代替本增量。entry/requirements固定hash不变：

- entry.py: `f936a4b18add4568356539f5499c482900f81286910ec3e6180633a4961082e6`
- requirements.lock.txt: `89cb0cca8c57c2e4a12d9947a9c6e5924ce10aefa163554640cf74f09c6e3287`
- 本次preflight-release.py: `cab67b5db35fdfc8a5496c731ecde08a49c66d3b51bc8305d670388cbd342659`
- 本次test_preflight.py: `8b891a33588155bcfab93faea2fecc24214b3ba8feb9678ebd651dc3e8a6410e`

## 轻量验证

- `.venv/bin/python -m pytest -q tests/test_preflight.py --junitxml=artifacts/preflight-venv.xml`：**36通过，0.88秒**。使用隔离release/本库DB、实际本地依赖metadata；测试中模拟sys.prefix，未对生产venv执行验收。
- pytest共2次：首轮35通过/1个夹具导入产生pycache的断言失败；夹具在importlib加载脚本前关闭bytecode后，36全部通过。保留首次日志，未放宽路径/版本/DB断言。
- Ruff format/check终态通过；CLI --help确认参数可用；git diff --check通过。
- 本增量完整构建/Chrome/服务启动/网络调用均0；不把旧131/15组或6组浏览器计作本增量重跑结果。
- 日志 `artifacts/preflight-venv.log` SHA256 `775ba9547e02c4e5b12e63cf3d379616c98f756258b1cc369239960fcad72625`；JUnit `artifacts/preflight-venv.xml` SHA256 `63d701add758419478c7704f3cd8e44d66cd1c42142ece7b61b30896b1a1f279`；首次失败 `artifacts/preflight-venv-before-fixture-fix.log`保留。

实际owned venv/release部署预检由集成按上面命令执行；本窗口未修改生产目录或重启作业。业务冻结及真实源/旧Watch/主域名/main边界不变。
