# D1 类型适配证据 · 2026-10-16

读取官方来源：[6551Team/opentwitter-mcp README](https://github.com/6551Team/opentwitter-mcp#websocket-real-time-subscriptions)及[官方 WSS 文档](https://docs.newsliquid.com/en/wss-services)。README中WSS tweet content示例有userScreenName、userIdStr、isReply、isQuote；事件表独立列出NEW_TWEET_QUOTE。未进行任何真实provider/付费/Watch请求。

总管夜间补充已批准本地接纳NEW_TWEET_QUOTE：作者可靠且没有回复/转推/矛盾证据时映射quote，引用对象不参与判断。NEW_TWEET仍以严格布尔结构分类；NEW_TWEET_REPLY/NEW_RETWEET在事件allowlist层排除。缺字段、非布尔或矛盾证据归unknown并隐藏；不靠RT正文或链接猜测。已知X稳定ID时还必须匹配userIdStr，否则要求作者handle严格匹配。

REST沿用原twitter_user_tweets请求及其includeRetweets=false过滤，仍要求作者及可靠结构；缺少类型布尔字段时不猜原创。REST类型样本不充分的响应会隐藏，不能把这一保守适配当作真实来源quote覆盖验收。WSS/REST共享全局账本，补全unknown只更新元数据、不产生新推文通知。

脱敏合成样本与回归在tests/test_feed_retention.py、tests/conftest.py；覆盖引用自己/其他追踪者/未追踪者、独立QUOTE事件、回复/转推/矛盾/未知、作者冲突、跨代及REST补全。实际6551端到端未测；未修改任何真实Watch flags或共享配置。
