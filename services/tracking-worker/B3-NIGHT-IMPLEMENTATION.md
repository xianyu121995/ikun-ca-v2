# B3 夜间实施补正

授权来源固定为 `579a57f2e3e470525eb53f9f1f85ba75d25f3728:docs/progress/NIGHT-RELEASE.md` / `night-release.json`。该记录批准 `4e0b293901c72df0c28180eb849a2d67d8c9c4c9` 协议，并解除完整构建/Chrome暂停；所有重任务仍使用原唯一heavy lock，整个预览生命周期持锁。

C03直接采用网站BFF的既有ManagedProjectsIpc/UDS，operation=ratings、contract=tracking-ratings-v1，严格body `{project_ids,expected_catalog_version}`；0—200唯一canonical ID，空数组核验全局版本。响应严格 `{contract,catalog_version,checked_at,items}`，found revision正整数，missing rating/revision均null，整集合不漏重。版本由Projects scope已提交project_changes最大sequence及boot nonce产生；重启/恢复/凭据轮换使旧版失效。

BFF把权威投影交Tracking bases/snapshots/pages。Worker不持有Projects方向凭据/Socket，不回调HTTP、不读取Projects库，不增加服务/总线/token。每次IPC≤2秒，整次feed≤8秒，评分批并发≤2，版本变化至多一次只读重取。页返回前复核本地语义版本及Projects版本；快照≤60秒不续期，limit可变，其余游标绑定保持原提案。默认S/A/B；C/D/null/missing诚实排除并计数，无rating=all。

先接Projects原owner最小constructor修复精确SHA，固定导出获审依赖及Auth `f097bd4722155d5e689b8894956391ed7e5f2fa7`，认证500必须消除。不得在preview改依赖源码或降500为成功。原失败证据保留。实现/测试结果另记，授权记录本身不构成PASS。

仅修改自有services/tracking-worker、schemas/tracking。无merge/push/deploy，无真实/付费/provider/Watch操作；默认外部来源关闭，页面明确“未连接真实来源”。语音由全站UI在B3冻结后接手，本模块仅提供经审新活动metadata。
