# 第二阶段规范冻结校验

规范：phase2-v1.0.0；规范提交以tag phase2-spec-v1.0.0定位。校验环境为本机Node24.22.0/pnpm10.33.1，主仓库main；未执行分支合并、真实API/平台请求、数据库迁移或生产部署。

## 本轮结果

- 9个原Worktree逐一核实Git HEAD与source-freeze.json一致，tracked/untracked状态clean；3个曾未冻结的窗口已保留已有成果正常提交，未amend/覆盖。
- packages/contracts build通过；pnpm typecheck通过contracts、runtime、hunter-worker、tracking-worker和website五个包。
- node scripts/check-phase2.mjs通过：规范文件hash、类型/字典枚举、固定scope/角色、四个DB/application_id、10个owner路径不冲突、9个源SHA与foundation祖先关系、UI0/后端依赖和暂停合并/生产标记。
- git diff --check通过；提交前对完整白名单暂存执行Git hygiene hook与cached diff检查。
- 校验脚本初次把Next的[...path]目录误判为父路径穿越；已改为按路径段判断.和..，保留该合法路由并复验通过。未修改任何业务候选。

## 验收边界

本轮证明规范一致与源版本可追溯，不证明业务已符合规范。未运行9个业务候选的全套回归/认证/浏览器/真实平台/组合链路，也未开展UI0新工作验收。Auth密码表单P0、最后33项未复跑/浏览器失败/格式检查失败、Hunter未执行硬化、Integration业务链路阻断均仍保留。完整限制见source-freeze.json与各原Worktree冻结文档。

本轮立即放行仅4个UI窗口；后端、集成、合并与生产继续held。未来完成门槛后仍须记录明确放行。
