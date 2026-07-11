import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@spawnd/ui", "@spawnd/api-client"],
};

export default nextConfig;
