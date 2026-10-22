import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker 部署用 standalone 产物（.next/standalone 自带精简 node_modules）；
  // 本地 dev / next start 不受影响
  output: "standalone",
};

export default nextConfig;
