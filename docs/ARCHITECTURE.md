# ikun.ca v2 第二阶段架构

规范phase2-v1.0.0；[服务和存储](phase2/STORAGE.md)、[API](phase2/API.md)、[放行](phase2/RELEASES.md)为当前基线。此轮只冻结设计，不实现运行封装或合并业务。

单仓库、三个独立服务/launchd作业：网站负责Auth与Projects，Hunter持有hunter.db，Tracking持有tracking.db。网站中的既有Python项目逻辑通过网站受托管私有IPC组件保留，不开放第四个独立业务TCP端口或作业；子进程跟随父服务退出。网站停止不停止两个worker。

四个物理数据库路径、归属与application_id见STORAGE；用户认证只在auth.db，各业务一个writer、一个迁移器。跨域只通过BFF/API/IPC与持久outbox/inbox，不做跨库事务。canonical注册与主页membership分离，人工加入监控不自动加入主页。

业务功能沿用本轮新写且冻结的9个v2候选，不复制旧版代码/库，也不为兼容问题重写一套同功能。新接口适配、认证P0、shared runtime迁移兼容、root依赖登记均等待对应批次放行。

资源仍按Mac mini M2/8GB：原生运行、串行构建、loopback/私有IPC、数据库与代码分离、Node LTS、provider调用默认关闭，驻留子进程计入实际RSS。生产路径、launchd、backup/rollback方案待最终组合验收；本次不部署、不改旧服务/Watch/Tunnel。
