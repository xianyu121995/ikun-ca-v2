# Hunter schema4 增量

B4唯一SQL权威为本目录001/002/003/004。原1/2/3及校验和保留，004新增研究保留账本/微秒起点/受控清理状态并解耦outbox外键，回填有稳定Target ID的旧发现，歧义必须回滚核对。只在显式init/migrate执行，serve/readiness不DDL；不读写其他库。升级前验证online backup，恢复先在不可激活临时文件合完整栅栏，最终原子发布到新hunter.db；严禁降版本号或删账本回退。精确SQL/hash及命令见services/hunter-worker/python/integration/RECEIVING-B4.json和README-B4.md，批准记录579a57f2e3e470525eb53f9f1f85ba75d25f3728。

以下基础阶段说明保留为历史：

# hunter.db 迁移归属

仅 hunter-worker 所有者可提交后续业务迁移。基础元数据由 packages/runtime 创建，版本 1。后续 SQL 采用 002_<name>.sql 递增；旧版数据不导入。业务表方案需在当前窗口实现前提交契约评审。
