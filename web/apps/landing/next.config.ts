import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  transpilePackages: ["@spawnd/ui"],
};

export default nextConfig;
