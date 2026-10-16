# 受保护v2测试站收尾验收（2026-10-17）

结论：本轮Tracking实时链路与安全/存储收尾通过；不代表完整Hunter真实发现链或主域名正式上线已验收。

- 网页实测4条：原创正常、自引真实原推卡片正常、新他引原作者Flaunch与原正文来自WSS quotedStatus，双帧补全未重复。旧他引按用户要求不补。
- 网站 `ed98cbb2d5fe383e67f2efe4738a641d24e86ae9`，正式build `gN_HFELurp87Frmkt2Xse`；Worker解析 `7e219afc30cca86b53efd075ae9caad2e47e1e81`。
- 三业务独立运行：web launchd/PID10956，Hunter launchd/PID78559，测试号Tracking独立launchd `ca.ikun.v2.c0lite.tracking-test`/PID14729。KeepAlive、RunAtLoad、30秒节流；原307d plist保留且未加载。测试号唯一处理范围0x2a_ikun，其他Watch无修改。
- 最新真实WSS connected，4条入库；本轮收尾供应商REST/Watch写均0。网站/Hunter/Tunnel进程在监听交接中不变。
- 四库不同物理inode、0600/单链接；4份在线备份integrity/FK通过。三域分别在独立副本删除真实领域记录及自身FK子记录，其他三库字节不变；正式库零删除。前两次副本演练的FK/主键错误保留，最终3项通过。
- 匿名应用401、内部无token401、错误scope403；公网无Cookie HTTPS403，证书校验通过。最初本机匿名测试因Host为127.0.0.1返回400，正确Host复核401。
- 5个临时账号全部禁用，admin有效；六份业务日志0600、未发现本机方向凭据值；原始帧日志仅测试号、0600、8MiB轮换保留3份。
- 三业务树RSS快照145.4MiB（非峰值/长期压测）。网站Next production/loopback/768MiB heap沿用；已保留网站回滚目录。

运行位置：`/Users/lvlei/Library/Application Support/ikun-ca-v2-c0-lite/target-test`；源码快照`release-integration/scripts/run_target_tracking.py`，配置均本机私有，密钥不入Git。原始帧在`target-test/logs/target-raw-wss.jsonl`。旧workspace帧日志与原307d配置均保留。

仍未验证：Hunter真实发现→人工加入的完整来源链；机器重启后恢复/当前作业故障注入；真实听感。无人值守定时备份未启用（本轮在线备份已完成）；LaunchAgent要求用户登录。主域名/正式环境未获发布批准，本轮未切换。没有主动破坏当前监听来伪造恢复验收。

机器回执：私有`release-integration/.runtime/first-real-sample/final-check-1792166598039402000/report.private.json`及`MANAGED-TARGET-ACTUAL.json`。监听持续开启。
