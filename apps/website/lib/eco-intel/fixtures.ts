import type { AccountType, Ecosystem, TrackChain } from './types';

/** Local defaults only. These rows are not sent to 6551 or twitterapi. */
export const FIXTURE_AT = '2026-10-26T00:00:00.000Z';

export interface FixtureSeed {
  handle: string;
  ecosystem: Ecosystem;
  role: string;
}

export const DEFAULT_SEEDS: readonly FixtureSeed[] = [
  { handle: 'BNBCHAIN', ecosystem: 'bsc', role: '官方' },
  { handle: 'buildonbnb', ecosystem: 'bsc', role: '官方' },
  { handle: 'PancakeSwap', ecosystem: 'bsc', role: '官方' },
  { handle: 'pinkecosystem', ecosystem: 'bsc', role: '发射台' },
  { handle: 'BinanceLabs', ecosystem: 'bsc', role: '官方' },
  { handle: 'DoraHacks', ecosystem: 'bsc', role: '黑客松' },
  { handle: 'cz_binance', ecosystem: 'bsc', role: '创始人' },
  { handle: 'heyibinance', ecosystem: 'bsc', role: '创始人' },
  { handle: 'solana', ecosystem: 'solana', role: '官方' },
  { handle: 'SolanaFndn', ecosystem: 'solana', role: '官方' },
  { handle: 'Pumpfun', ecosystem: 'solana', role: '发射台' },
  { handle: 'SuperteamEarn', ecosystem: 'solana', role: '官方' },
  { handle: 'toly', ecosystem: 'solana', role: '创始人' },
  { handle: 'rajgokal', ecosystem: 'solana', role: '创始人' },
  { handle: 'ethereum', ecosystem: 'eth', role: '官方' },
  { handle: 'ethereumfndn', ecosystem: 'eth', role: '官方' },
  { handle: 'ETHGlobal', ecosystem: 'eth', role: '黑客松' },
  { handle: 'EFDevcon', ecosystem: 'eth', role: '官方' },
  { handle: 'virtuals_io', ecosystem: 'eth', role: '发射台' },
  { handle: 'base', ecosystem: 'base', role: '官方' },
  { handle: 'buildonbase', ecosystem: 'base', role: '官方' },
  { handle: 'CoinbaseDev', ecosystem: 'base', role: '官方' },
  { handle: 'clanker_world', ecosystem: 'base', role: '发射台' },
  { handle: 'zora', ecosystem: 'base', role: '官方' },
  { handle: 'jessepollak', ecosystem: 'base', role: '创始人' },
  { handle: 'farcaster_xyz', ecosystem: 'base', role: '官方' },
  { handle: 'RobinhoodCrypto', ecosystem: 'robinhood', role: '官方' },
  { handle: 'RobinhoodApp', ecosystem: 'robinhood', role: '官方' },
  { handle: 'arbitrum', ecosystem: 'robinhood', role: '官方' },
  { handle: 'vladtenev', ecosystem: 'robinhood', role: '创始人' },
];

export const STUB_TWEETS = [
  {
    id: 'tw_fixture_hackathon',
    handle: 'ETHGlobal',
    text: 'ETHGlobal 黑客松本周开启，欢迎新协议团队报名。',
    url: 'https://example.invalid/eco-intel/hackathon',
  },
  {
    id: 'tw_fixture_launch',
    handle: 'base',
    text: '开发者资助计划将于下周上线，并开放融资咨询。',
    url: '',
  },
  {
    id: 'tw_fixture_noise',
    handle: 'solana',
    text: 'gm builders',
    url: '',
  },
] as const;

export const STUB_FOLLOWS: readonly {
  id: string;
  handle: string;
  seed: string;
  type: AccountType;
  chain: TrackChain | '';
  name: string;
  bio: string;
  summary: string;
}[] = [
  {
    id: 'fol_fixture_bsc_protocol',
    handle: 'bscvault',
    seed: 'cz_binance',
    type: 'protocol',
    chain: 'bsc',
    name: 'BSC Vault',
    bio: 'DeFi protocol and bridge fixture on BSC. Not a live account.',
    summary: 'Fixture: oracle and wallet infra testnet.',
  },
  {
    id: 'fol_fixture_protocol',
    handle: 'newproto_xyz',
    seed: 'solana',
    type: 'protocol',
    chain: 'solana',
    name: 'New Proto',
    bio: 'Onchain protocol fixture on Solana. Not a live account.',
    summary: 'Fixture summary: testnet announcement.',
  },
  {
    id: 'fol_fixture_eth_launchpad',
    handle: 'ethpadfi',
    seed: 'ETHGlobal',
    type: 'launchpad',
    chain: 'eth',
    name: 'ETH Pad',
    bio: 'Launchpad fixture on Ethereum. Not a live account.',
    summary: 'Fixture: upcoming protocol launch.',
  },
  {
    id: 'fol_fixture_launchpad',
    handle: 'padlaunch',
    seed: 'base',
    type: 'launchpad',
    chain: 'base',
    name: 'Pad Launch',
    bio: 'Launchpad fixture on Base. Not a live account.',
    summary: 'Fixture summary: upcoming launch.',
  },
  {
    id: 'fol_fixture_hood_hackathon',
    handle: 'hoodhack',
    seed: 'vladtenev',
    type: 'hackathon',
    chain: 'robinhood',
    name: 'Hood Hack',
    bio: 'Official hackathon track host fixture on Robinhood Chain. Not a live account.',
    summary: 'Fixture: hackathon registration open.',
  },
  {
    id: 'fol_fixture_token',
    handle: 'meme_token',
    seed: 'solana',
    type: 'token',
    chain: 'bsc',
    name: 'Meme Token',
    bio: 'Memecoin and personal token fixture. Not a live account.',
    summary: 'Fixture: token chatter only.',
  },
  {
    id: 'fol_fixture_kol',
    handle: 'kol_noise',
    seed: 'toly',
    type: 'kol',
    chain: 'eth',
    name: 'KOL Noise',
    bio: 'KOL account fixture. Not a live account.',
    summary: 'Fixture: commentary, no protocol.',
  },
  {
    id: 'fol_fixture_exchange',
    handle: 'desk_exch',
    seed: 'BNBCHAIN',
    type: 'exchange',
    chain: 'bsc',
    name: 'Desk Exchange',
    bio: 'Exchange brand fixture. Not a live account.',
    summary: 'Fixture: venue, not a project.',
  },
  {
    id: 'fol_fixture_person',
    handle: 'some_person',
    seed: 'toly',
    type: 'founder',
    chain: '',
    name: 'Some Person',
    bio: 'Personal account fixture. Not a live account.',
    summary: 'Fixture summary: no project signal.',
  },
  {
    id: 'fol_fixture_pending',
    handle: 'vagueacct',
    seed: 'base',
    type: 'unclassified',
    chain: '',
    name: 'Vague Account',
    bio: '?',
    summary: '',
  },
];
