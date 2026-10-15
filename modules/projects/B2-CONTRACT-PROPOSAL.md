# B2 主页增量提案（待总管审阅，未作为已放行契约实施）

基线 phase2-v1.0.0 + auth-b1-final-v2；项目基线 7f8a461；建议增量名 projects-home-v1。不改变 ProjectRecordV2、canonical ID、Auth、worker 命令或三服务边界。

1. 独立重要事件：建议项目详情/写入额外投影 `milestone: {date: YYYY-MM-DD|null, hour: '00'..'23'|null, title: string, status: confirmed|estimated|unconfirmed}`；时区固定 Asia/Shanghai。与 token_date 独立，未知小时不补 00；事件修改与项目字段在同一事务/同一 revision/同一幂等操作提交。
2. 全量查询：建议 GET projects 增加 `discovered_on`（北京时间自然日）、`sort`（rating/name/discovered/progress）、`direction`；cursor 绑定固定 scope、完整条件和排序，数据库在分页前过滤排序。重要事件查询独立，不沿用搜索/发现日期条件。固定 UI 内部仍有按已加载资料排序/9 条切页的展示逻辑，不能伪称其为服务器全量查询；需确认由适配回调注入查询状态及页数据的最小扩展，不改用户定稿样式。
3. 完成/恢复：建议 POST `/projects/{id}/completion` 和 `/projects/completions`（批量），只接受已验证 superadmin，If-Match/逐项 revision、UUID 幂等。完成操作原子保存 previous_stage、previous_percent、完成时间，设置 completed + removed；普通主页 remove 不改变进度。恢复 POST `/projects/{id}/restore` 原子恢复真实原进度和 active。重复恢复不产生新 ID；新建即完成的恢复起点须明确定义（建议新建草稿保存前的 progress_stage，而非虚构历史）。
4. 操作回执：建议只读 `/projects/operations/{idempotency_key}`（同 actor/scope/route）供超时 reconcile；不以重复写入猜结果。HTTP 200/201 只表示本库同步事务完成，202/unknown 不代表 Tracking 已运行。

请总管确认字段/路由/回调增量及接收规范版本。批准前继续实施已有 phase2 的 CRUD、canonical、membership、可信身份、私有IPC、迁移和事件回执/outbox；小时事件/完成恢复及其 UI 实写保持未接入，不截断字段或模拟成功。
