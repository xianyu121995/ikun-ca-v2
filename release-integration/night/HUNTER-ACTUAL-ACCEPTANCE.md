# Hunter 真实维护验收

2026-10-16T20:59:27.216994+08:00 完成，候选 `9a53f73f6c2c3f588497c35018074549723ef7d6`。唯一005已将原库4→5，固定F9 reader恢复，launchd PID **78559**，ready200、外采false。

- 猎手 **90 = 原2完整保留 + 新88停用pending**；新身份/粉丝/通道仍NULL，baseline/watch均未ready。新增私有事实/收据 **6575/6575**。
- 同包重放新增 **0/0/0**，全部逻辑指纹不变；首轮原run和source/package/ownership已核对。原2包含两重试字段的当前完整行，以本停窗最新快照保留；旧schema4基线引用和两次失败证据归档。
- 同停窗副本演练先通过，原库完整指纹仍未变才005/apply；成功窗口 **13份**运行库备份均完整性/FK通过，连此前失败窗口共 **21份**（原迁移器自己的备份另计）。四库原路径/inode保持，没有DB覆盖或降级。
- 网站54011完整树及IPC、Tracking25225、Alpha9034、PG79494、两个Tunnel和其他保护身份/配置保持。未改主域名/Cloudflare/main，未重复旧端stop。
- 本轮外部API/Watch写/通知/命令/公开事件/Next构建 **全部0**。停服意图至恢复核验 12.575s，仅运维窗口测量。

实际receipt SHA `1e7c15c7eb3f8f737f1a41ae938546a1559356bce86f63589069efc9102faa6c`；停窗演练SHA `83400e228ab66818faed1e489e581c69f14781dc513b776bf2a9720cbfb0efa4`。32本地夹具和封存函数验证通过，不与历史用例重复相加。

剩余：Tracking实际维护未批准/执行；真实样本、整体实时数据流和24小时稳定验收尚未完成。Tracking最小草稿及Alpha4项纯本地夹具已在critical-preparation-20261016-c1保存，未启动真实observer。
