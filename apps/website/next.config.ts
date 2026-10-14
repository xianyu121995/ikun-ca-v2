import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  serverExternalPackages: ["@ikun/runtime"],
  experimental: { cpus: 1 },
};
export default config;
