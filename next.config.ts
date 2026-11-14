import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/science/:path*", destination: `${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/:path*` }];
  },
  experimental: { proxyTimeout: 120_000, proxyClientMaxBodySize: "260mb" },
};
export default nextConfig;
