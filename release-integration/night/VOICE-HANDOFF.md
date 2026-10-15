# 语音集成：本地冻结，尚未部署

状态 **LOCAL_FROZEN_NOT_DEPLOYED**。可审源码候选 `ee67190d5ac83f87f90dbd188e9b41239460eb33`，网站运行字节提交 `5e32a35663036997812ebe8c758220f885015b0a`，生产 BUILD_ID `toKW74u9T1cCk_lyTUZXo`。328源码/271compiled逐项匹配，工作区产物已完成；实际 v2 仍为 `64088893841122491aba508fdb514507db3d9339` / `QTLRQ2vGatyCJCEhtFEVA`，语音未启用到公网。

已接收库 `684d4013d97118612cdfbdc77d32adfc22704af8` / 根批准 `6f6ba3c4e5ca0fcea4b98873faf340da64082eac`，只cherry-pick其16路径增量，未收父分支网站/demo历史。公共index仅追加一行导出。原77来源检查、B3原62来源与精确preflight例外、B4/C03和8个主页冻结检查保留；实际旧哈希保持数改为逐项计算70，而非沿用忽略C03例外的旧硬编码75，来源检查没有减少。

网站仅四份接线：Tracking page经真实B1取user_id和每页非秘密UUID epoch；TrackingLive复用唯一已有EventSource，并转交open/error/401/退出/清理；新tracking-voice桥接与metadata适配器。metadata只读既有单订阅和Projects接口，核对成功envelope、实际ID、正revision，单请求2秒、库总预算4秒，401撤销会话，沿signal取消。不从事件或当前feed页猜备注/评级，没有新HTTP、业务库、队列服务或第二条流。个人设置适用于user与superadmin，业务只读规则保持。

只用本机Web Speech音色、默认关闭、每页真实手势启用；原库负责原创/引用/live/wss/非replay、22—08上海静音、TTL/队列/去重与取消。`localService`与用户瞬时激活接口已核对：[MDN本机音色](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService)、[MDN用户激活](https://developer.mozilla.org/en-US/docs/Web/API/UserActivation/isActive)。未实际扬声，未调用真实/付费来源。

本地生产Next无声页面 **48项** 通过：两角色、真实B1及实际订阅/Projects metadata、空feed仍能取得权威备注评级、唯一Tracking流、普通用户个人开关和只读业务界面、原推/引用与去重/replay、逐账号/全局关闭、断流/重新手势、晚到metadata丢弃、22点取消/08点不补播、真实B1禁用后静默SSE取消、晚到open不能复活旧epoch、API401及退出。浏览器注入无声Speech替身、模拟时间和SSE帧；不是实际WSS，也没有往生产Worker写种子。正式bundle扫描未发现测试注入标记。

metadata适配器12项通过；冻结语音库原32项同套复验通过，chief独立同套不累计。生产UI/Next build、网站typecheck通过。首次从根目录跑库测试缺TSX配置导致React未定义；补正确`TSX_TSCONFIG_PATH`后原32通过，没有为此改库或重复构建。

不可变页面证据提交 `6e6e7b6d3692b8e4b108fbba3b823c7a028096ce`。最终第二批48项对应私有 `run-1792095246818597000/` 的tested-harness.py、原receipt副本与四张1440/390截图，全部hash已核对并视觉检查。首批admin390截图出现重复重绘区域，只加测试截图前fonts.ready/两帧rAF等待后复跑同一构建；原图在initial-screenshots，两次48回执保留，不算96。今后截图写独立run目录。

实际升级命令曾固定为：

```sh
/Users/lvlei/.local/bin/python3.11 release-integration/scripts/upgrade_voice_site.py --candidate ee67190d5ac83f87f90dbd188e9b41239460eb33
```

该**同一命令两次被自动审批拒绝，均未创建进程**。第一次理由为“现有可信用户内容未明确批准这次语音版本部署，不能仅依据助手或总管转述放行”；通过read_thread核对夜间原始userMessage并重交后，第二次仍认定工具读取与转述不足以建立可信授权，原禁止正式发布要求继续适用。未换工具/窗口执行，未创建语音release、语音备份或公网语音测试账号，也未启动语音公网验收。下一步需要本聊天用户明确批准最终完整候选SHA。此报告提交会前进HEAD；脚本要求candidate==HEAD，最终批准问题及待执行命令须使用报告后实际完整HEAD，并再次核对与ee候选相同的328/271字节，不直接运行上述历史命令。

批准后已有升级包装器会先在线备份四库，再调用已验website upgrade，仅重启新v2网站与其私有Projects IPC。它强制比对Hunter原75b及Tracking原640的PID、plan/env/plist字节和四库inode不变。网站ready失败沿既有机制恢复原web plist/env/owner，保留原release与全部库，不降schema或覆盖库。此轮因审批拒绝，**没有实际触发该升级或回滚**。

拒绝后只读核验：现有三ready正常、四库身份/integrity/FK通过，Hunter与Tracking既有job未变，B3两个临时用户仍禁用、原admin有效。后续审计拷贝为独立post-refusal-runtime-audit文件，路径及hash见voice-acceptance.json。B3旧fixed latest-audit路径被本次后续只读审计更新，原历史hash保留于B3报告，不声称该latest路径仍保存原204.6MiB快照字节；原公网证据、B3跟踪摘要及chief当时独立核验保持。

语音公网默认关闭/权限/撤销/临时用户收尾尚未执行。还未验证真实听感和真实来源；原`ingest/tracking`501及正式域名/旧版边界保持。main为`63e8a2857241c6a76226f21435e40db9736a1e7e`，没有域名、Cloudflare、旧服务或共享Watch变动。

机器可读状态：[voice-acceptance.json](./voice-acceptance.json)。源码/patch：[voice-source-binding.json](./voice-source-binding.json)；本地测试与不可变截图来源：[voice-local-acceptance.json](./voice-local-acceptance.json)；构建与纠正loader记录：[voice-build-evidence.json](./voice-build-evidence.json)。
