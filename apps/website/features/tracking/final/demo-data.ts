import type { Account, Grade, Post } from "./model";
/** Fictitious posts and metrics copied from the approved UI reference, not X data. */
const accountRows = [
  ["Hyperliquid", "HyperliquidX", "S", "重点关注主网上线", "H"],
  ["EigenLayer", "eigenlayer", "A", "再质押生态进度", "Ξ"],
  ["Uniswap Labs", "Uniswap", "A", "关注 v4 上线进度", "U"],
  ["Blur", "blur_io", "B", "API 限额调整", "BL"],
  ["Friend.tech", "friendtech", "B", "社区活跃度观察", "F"],
  ["Coinbase", "coinbase", "B", "新产品发布", "C"],
  ["Arbitrum", "arbitrum", "B", "L2 生态跟踪", "A"],
  ["Optimism", "Optimism", "B", "生态发展动态", "O"],
  ["Base", "base", "A", "开发者工具更新", "C"],
  ["Aave", "aave", "S", "借贷产品版本升级", "A"],
] as const;
const postRows: [number, number, string, string, string, string, boolean, string, string, string][] = [
  [1, 12, "Introducing HyperEVM mainnet. A fully on-chain, high-performance execution environment built for the next generation of applications. (Demo post)", "342", "1.2K", "4.8K", true, "HyperEVM", "Mainnet Update", "teal"],
  [2, 28, "Restaking is just the beginning. Today we’re excited to share the next phase of our roadmap. More details in the blog below. (Demo post)", "156", "412", "1.9K", false, "EigenLayer", "Next Phase", "violet"],
  [3, 68, "Uniswap v4 hooks are changing what’s possible. New tools, new integrations, and a more open DeFi ecosystem. (Demo post)", "312", "876", "3.1K", true, "Uniswap v4", "Product Demo", "pink"],
  [4, 119, "API rate limits have been updated. Developers can now request higher limits for production use cases. (Demo post)", "89", "230", "712", false, "BLUR", "Developer Update", "orange"],
  [5, 185, "Community call this Friday. We’ll discuss recent progress and answer questions from the community. (Demo post)", "64", "142", "530", false, "friend.tech", "Community", "blue"],
  [6, 290, "Base is for everyone. More builders, more users, more onchain apps. (Demo post)", "201", "498", "2.4K", false, "BASE", "Ecosystem", "navy"],
  [1, 419, "A quick development update: this week we focused on improving developer tooling. (Demo post)", "97", "263", "1.1K", false, "", "", "teal"],
  [10, 602, "Our next lending protocol upgrade is under review. Documentation will follow. (Demo post)", "133", "309", "2.1K", true, "Aave", "Protocol Update", "navy"],
  [9, 887, "A new set of developer resources is available for onchain builders. (Demo post)", "78", "242", "986", false, "BASE", "Developers", "blue"],
  [7, 1628, "More tooling and ecosystem updates from the Arbitrum community. (Demo post)", "64", "124", "853", false, "Arbitrum", "L2 Ecosystem", "navy"],
  [8, 1999, "An ecosystem note from the Optimism community. Thanks to everyone building together. (Demo post)", "71", "122", "901", false, "OP", "Ecosystem Update", "orange"],
  [6, 3200, "More onchain experiences are coming to the ecosystem. (Demo post)", "101", "246", "1.5K", false, "", "", "teal"],
];
export function createDemoData(now: number) {
  const accounts: Account[] = accountRows.map(([name, handle, grade, note, avatar], index) => ({ ui_key: `demo-account-${index + 1}`, name, handle, grade: grade as Grade, note, avatar, status: "running" }));
  const posts: Post[] = postRows.map(([account, minutes, body, comments, reposts, likes, important, title, caption, theme], index) => ({
    ui_key: `demo-post-${index + 1}`, account_key: `demo-account-${account}`, published_at: new Date(now - minutes * 60000).toISOString(), body, comments, reposts, likes, important,
    media: title ? { kind: "demo", title, caption, theme } : null,
  }));
  return { accounts, posts };
}
