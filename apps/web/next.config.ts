import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@realm/types", "@realm/ui"],
};

export default nextConfig;
