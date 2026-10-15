# B0 收尾后的剩余阻断

**B0在本轮授权范围内无未关闭项，基础设施验收通过。** 用户禁止合并、部署并要求业务冻结，所以实际源码收件、领域适配和生产验证保留到对应阶段；不把它们写成B0已实现能力。

| 编号 | 阻断内容 | 归属与解除门槛 |
|---|---|---|
| AUTH-OPEN | 登录系统开工尚未获用户单独放行 | B1；用户明确授权，范围与冻结基线按AUTH-RELEASE.md |
| AUTH-P0 | 含密码HTML表单默认GET风险仍在冻结候选 | B1首修；同源POST、生成UI一致、无JS与浏览器回归通过 |
| AUTH-QA | 最终33项未复跑、Next移动端重置密码smoke未完成、原格式检查失败 | B1；新SHA完整回归/浏览器/格式与hook证据 |
| AUTH-CONTRACT | session capabilities、用户列表分页、重置/PATCH/退出/改密DTO及schema权威尚未对齐 | B1；可信principal、scope/权限/SSE与Auth2受控版本/校验和验收，不修改其他业务库 |
| PROJECTS | 私有IPC真实Python领域入口、唯一身份、canonical/outbox/receipt尚未适配；小时事件、全量日期查询及完成恢复与旧DTO有差异 | B2；按ADAPTER-GAPS/收件计划形成明确契约增量和授权事务，保留既有CRUD，不新增第四服务 |
| TRACKING | 订阅ID与项目ID映射、服务凭据/可信actor、命令回执和未知状态恢复未完成组合验收 | B3；领域权威迁移/校验和、restart及命令链；媒体/互动/重要标记缺数据时保留未知 |
| HUNTER | 手工confirmed到项目/Tracking的回执链、公开DTO与真实来源尚未组合；先前拒绝的硬化动作未执行 | B4；接收链与脱敏、72h/generation/baseline证据；不绕过先前审批、不改共享Watch |
| RECEIVING | 正式UI包/样式/页面、Auth和业务源尚未收件到主站 | C0及授权收件；固定最终SHA、唯一AppShell/组件、正确lock及路由；本轮只完成reviewed_not_executed计划和临时消费测试 |
| E2E | 真实认证到发现、确认、订阅、活动和主页的组合链路未验收 | C0；各领域先验收，单独取得组合/合并授权，fixture与真实平台证据分开 |
| PRODUCTION | 8GB长期压力、实际launchd、TLS/Access、独立凭据、online backup/restore与发布回滚未验收 | D0；C0通过后逐项验证，生产动作需用户明确批准 |

主仓库原未跟踪候选，以及Hunter Worktree未跟踪ui目录原样保留；不作为验收输入，不清理、不覆盖。GitHub私有远程/团队保护按原规划另行配置，不把本地Git提交当远程保护已生效。

旧phase2文件中“Tracking四列阻断尚未修复”和旧B0候选中的“B0进行中”是冻结时的历史记录。当前收尾已通过新B0对三/四列兼容、校验和错拒绝和失败回滚测试；不声称原f89d8f5旧二进制已被修改或可直接处理所有新库。
