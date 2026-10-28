import type { NextConfig } from "next";

// Node resolves "localhost" to IPv6 first, while uvicorn listens on IPv4 by default.
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "").replace("//localhost:", "//127.0.0.1:");

const nextConfig: NextConfig = {
  output: "standalone",
  // The demo sandbox cookie must be first-party, so sandbox calls go through this origin.
  async rewrites() {
    return [{ source: "/api/sandbox/:path*", destination: `${API_URL}/api/sandbox/:path*` }];
  },
};

export default nextConfig;
