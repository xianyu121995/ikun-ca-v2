# 首次真实样本操作包（尚未监听）

预检fc45a1b已验：0x2a_ikun=1389粉丝/REST，Watch115，NEW_TWEET80/600，余520，目标不存在；实际供应商请求仅2次。另一名WSS候选来自真实迁入UUID和当前启用newFlwBol的自有条目，身份只在私有文件，仍待fresh profile证实>=5000；不符就停，不换第三号。

原样本源码已准确独立收件：Hunter1e0d0b06、Tracking704e6214；原fingerprint命令离线通过（H29887bb7，T1610d883）。不替换常驻F9/307d，不重建网站，不触main、ikun.ca、Cloudflare、Alpha配置或已有Watch。

## 命令入口与顺序

私有根目录：`release-integration/.runtime/first-real-sample/next-stage/`。本轮只完成默认dry-run，以下带动作参数必须等根批准对应准确plan/argv，且用户先待命。不是立即发推通知。

1. 在已登录B1的v2会话走原BFF操作：新增0x2a Hunter（enabled=false），两名fresh profile、原prepare-supplement-v2/离线apply补证已有目录，真实PATCH启用及原Store.apply_profile。严格按原v3 fixture顺序，保留真实POST/PATCH operation_receipts/CAS/actor/时间，不能SQL造身份或fake ready。setup停窗使用下面窗口工具purpose=setup，离线CLI真正退出后才restore。
2. 在**停稳的Hunter sample窗口**收集原owner manifest/gates/setup及三份前置证据，`sample_hunter_argv.py --bind`只绑定真实文件并生成原check/run argv。先原CLI check；再原CLI run，建议<=30秒、REST=baseline_only静默，WSS仅原自有条目。原一次消费STATE_KEY不清；无自然事件不得宣称Hunter真实发现/REST交付。
3. Hunter子进程确实退出后restore F9 hard-off。随后用户仍待命时开始Tracking新号阶段：fresh target profile→完整Watch before一读→最多1次新Watch add并保留原回执/实际已审request（不做setup after读取）；新建原Projects POST201及正式reconcile，再通过原Tracking BFF创建真实sub，最后superadmin确认。不要提前新建耗掉300秒。
4. Tracking独立sample停窗后用该窗口的真实snapshot、command_id及原回执构建late JSON；`sample_tracking_inputs.py --mint`生成原NewProof/Authorization/原CLI argv。严格<=300秒，观察最大120秒且按最老事实剩余时间裁剪；过期/旧记录/未confirm/既有目标Watch/原flags组变化均拒绝。
5. `sample_tracking_launch.py --execute`仅exec原704 CLI（--serve --execute），4012沿原BFF/SSE，原方向凭据保持，6551别名仅在此有限子进程内存。**收到实际WSS/HTTP就绪证据后**根/Claude才通知用户发原创、自引、他引。结束后子进程实际退出、DB/端口fence通过，再restore307d hard-off。

```sh
sample_ops='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/scripts'
sample_stage='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/integration/release-integration/.runtime/first-real-sample/next-stage'
sample_py='/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/venvs/tracking/bin/python'
sample_static="$sample_stage/sample-static.private.json"
sample_sha() { "$sample_py" -c 'import hashlib,sys;from pathlib import Path;print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())' "$1"; }
# Alpha只读双DTO。仅在实际短窗口启动；不改Alpha，不发请求/新WSS。
"$sample_py" "$sample_ops/sample_alpha_witness.py" --plan "$sample_stage/alpha-observer-plan.private.json" --plan-sha256 "$(sample_sha "$sample_stage/alpha-observer-plan.private.json")" --observe
# 独立终端/执行cell：prepare只读封存当时准确PID/树。role可为hunter，purpose可为setup。
"$sample_py" "$sample_ops/sample_writer_window.py" prepare --role tracking --purpose sample --static "$sample_static" --plan "$sample_stage/arm/tracking-window.json"
"$sample_py" "$sample_ops/sample_writer_window.py" stop --plan "$sample_stage/arm/tracking-window.json" --plan-sha256 "$(sample_sha "$sample_stage/arm/tracking-window.json")"
# late-inputs.private.json必须来自本轮真实API回执和stop输出的snapshot，不是模板数据。
"$sample_py" "$sample_ops/sample_tracking_inputs.py" --static "$sample_static" --static-sha256 "$(sample_sha "$sample_static")" --late "$sample_stage/arm/tracking/late-inputs.private.json" --late-sha256 "$(sample_sha "$sample_stage/arm/tracking/late-inputs.private.json")" --mint
"$sample_py" "$sample_ops/sample_tracking_launch.py" --static "$sample_static" --static-sha256 "$(sample_sha "$sample_static")" --argv "$sample_stage/arm/tracking/original-cli-argv.private.json" --argv-sha256 "$(sample_sha "$sample_stage/arm/tracking/original-cli-argv.private.json")" --window-plan "$sample_stage/arm/tracking-window.json" --window-plan-sha256 "$(sample_sha "$sample_stage/arm/tracking-window.json")" --execute
# 原有限CLI退出后；实际PID/start仍活着则拒绝恢复，不能只看端口空闲。
"$sample_py" "$sample_ops/sample_writer_window.py" restore --plan "$sample_stage/arm/tracking-window.json" --plan-sha256 "$(sample_sha "$sample_stage/arm/tracking-window.json")" --sampler-process "$sample_stage/arm/tracking/sampler.process.private.json"
```

Hunter绑定入口：`sample_hunter_argv.py --static ... --static-sha256 ... --index <真实owner输入index> --index-sha256 ... --bind`。输出原check/run的完整私有argv；check用原H venv并设PYTHONPATH到收件1e0源码。run用`sample_hunter_launch.py`及本域真实window plan，原CLI要求执行期0600临时secrets-file，结束删除。该处理须根明确允许`allow_execution_temporary_secret_file=true`；旧.env不改、REST key与6551 token绝不混用。当前没有物化密钥文件。

## 还缺的真实输入 / 预算

- Hunter：两条fresh profile、已验目录的真实补证approval及prepare-supplement-v2包、原真实POST/PATCH回执、当前revision/generation/account_state、实际root_review_sha，以及原manifest/gates/setup index；时间和UUID来自原服务/副本，不能借演练数据。
- Tracking late字段：tracking_snapshot、projects_reconcile、setup_profile、watch_before、watch_creation、watch_request（各path/sha256），identity_observed_at/watch_created_at/approved_at/create_command_id。Projects证明只能原`GET /api/v1/projects/operations/<key>?method=POST&path=%2Fapi%2Fv1%2Fprojects&contract=phase2-v1.0.0`；Tracking创建走`POST /api/v1/tracking/subscriptions`，字段project_id/name/x_user_id/x_handle/notes/confirmed=true，实际command_id从原返回取。备注用于播报、评级仍归Projects。
- Alpha：实际只读observer的不可变initial/滚动见证。28个名单已只读准备排除摘要，未猜稳定XID；源漂移/重连/健康异常锁定本轮healthy=false。仅5项定向测试中的合成Alpha循环跑过1秒，真实observer未启动。
- **拟另审上限**：Hunter setup 2 profile+1Watch；Hunter观察2profile+1Watch+1Following20/1WSS；Tracking setup 1 fresh profile+before Watch1+新Watch1；after由原观察段已有Watch一读完成，严格active/额度/reconcile通过后才WSS；Tracking观察3只读/1WSS。额外最多12只读+1新增，含已花预检累计14只读；两个WSS串行、无重连/自动重试，不能藏进原预算。未知写结果停下，只允许已列只读回查，不盲重试/删重建；不修改已有条目。新测试Watch先保留，不擅自多做删除/更新。

窗口工具复用原Journal锁/stop_web_once/备份/兼容restore；每窗口四库before/stopped/after各一组，原库不覆盖、schema不降、仅本域独立writer。sample restore必须核真实sampler PID/start已退净，未知bootstrap不重试。缺late事实的工具只打印WAIT，不发许可/不连运行DB。

5项定向夹具（1.164s）及6个本地CLI dry-run通过；第一次用全局Python缺websockets，已改用现有Tracking venv验证，未安装依赖、未扩展全套。少量胶水只生成输入/启动原CLI和适配已验停启，不新增业务/总控。当前真实供应商仍2次、Watch写/WSS/真实新记录/真实observer均0。

当前已进入22:00–08:00静音时段，严格保留。今晚最多证明网页数据和夜间静音；实际新推听感须非静音时段单列，不能回播夜间历史或清一次fence冒充。整体真实链路、听感、24小时稳定仍未验收。

计数补正：setup_watch_read_attempts=1仅代表实际before一读；不再要求/伪造watch_after快照。add原回执必须提供真实新id和已分配twGroupId，实际已审request/返回字段须足够构造完整expected flags；不足报ADD_RECEIPT_ASSIGNED_GROUP_UNPROVEN或ADD_EXPECTED_FLAGS_INCOMPLETE，停止发许可。观察段原三读不变，原Remote.watches归一化后的实际行由原reconcile/strict-active/额度验证后才连WSS，不能把expected proof说成已回查事实。
