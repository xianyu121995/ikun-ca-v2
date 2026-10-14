# ikun.ca API 冻结规范

当前权威版本：**phase2-v1.0.0**。完整接口、字段、权限、项目和订阅ID、幂等/版本、人工确认和事件回执见 [第二阶段 API](phase2/API.md)。机器字典见 [contract.json](phase2/contract.json)，类型见 packages/contracts/src/phase2.ts。

固定scope ikun-main，人类只有superadmin/user；业务身份由Auth/BFF验证。公共 /api/v1、内部 /internal/v1；标准data/error/request_id、cursor、If-Match与UUID幂等键。主页移除保留canonical与监控引用，不自动操作worker。

基础提交f89d8f5当前已实现的仅health与idle worker status，公开业务catch-all仍503，内部业务仍501；这些运行门禁未由规范提交改变。各窗口已有候选与规范存在差异，需按 RELEASES.md 分批适配后再验收，不把目标接口当成已实现接口。

第一阶段原文可用 git show foundation-v0.1.0:docs/API.md 阅读，只作历史，不再使用其中不同scope示例、含糊GET/POST权限、旧summary或自动暂停描述。
