# 正式收件审阅结论

config/b0/receiving-plan.json是本轮完成的执行方案，状态reviewed_not_executed。原分支与source pin保持不变；本轮没有源码分支合并、页面搬运、root lock启用或实际路由接线。

1. 公共UI固定486294a（视觉a648e3d）；主页eb93ac7、Hunter08065d7、Trackingd90598f。未来按唯一@ikun/ui workspace依赖和config/b0/pnpm-ui-lock.yaml收件，保留用户认可的normalize样式与一个AppShell。此次临时Next页面已实际消费组件、CSS并成功静态渲染；测试路由只在临时目录，未提交主站。
2. 业务按Auth→Projects→Tracking→Hunter的依赖收件，最终来源必须使用各阶段新验收SHA；现在的aa3cf65等只是保留基线，不是待直接合并的已通过版本。C0组合/合并须另行批准，不能把B0收件计划当执行许可。
3. 每次收件先核对owner路径、schema/contract差异、来源/hash、测试和回滚证据；root依赖/lock/layout/globals/proxy/health接线归总管。窗口只在自己的模块留integration候选，不能因API子目录归属覆盖全站入口。
4. foundation元数据定义及校验和唯一来源为packages/runtime/src/stores.ts。显式初始化可给旧v1增补独立_migration_checksums记录；只读readiness不增补。校验和错/未来SQLite user_version/未知迁移版本拒绝，失败事务回滚并保留数据；不覆盖旧checksum列或代替领域迁移。
5. 每个物理库从自己的版本2开始，由领域owner的唯一迁移器与schema/checksum权威负责。Auth现有auth_migration_checksums与内嵌SQL/审阅SQL需在B1给兼容收敛方案；Tracking既有checksum列可兼容读取，新校验和按共享规范。不能同时让Next与Python迁移/写projects.db。
6. B0启动/readiness默认支持foundation1，防止未经审查自动接纳业务2。B1预览/后续收件必须明确声明Auth2并校验其scope/schema；B2由Projects IPC入口负责自己的库。不得通过maximumVersion=999或删除标记解决版本冲突。
7. UI定稿与API差异已逐项归入ADAPTER-GAPS：小时事件/完成恢复/全量查询归B2，Hunter投影/隐藏身份归B4，Tracking身份/媒体等归B3，公共包样式收件归C0。保持当前phase2业务契约，所需增量由对应阶段另审，不由B0静默扩展。

本轮接入能力仅基础设施和合成health；未运行Auth业务回归、真实Projects CRUD、监控provider、SSE业务或生产验证。B0通过只满足B1的一个前置，后端保持held。
