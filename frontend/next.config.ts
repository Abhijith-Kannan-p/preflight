import type { NextConfig } from "next";

// Where this server forwards /api/sandbox/* (baked in at build time). API_INTERNAL_URL is for
// when the server reaches the API by another name than the browser does (Docker Compose:
// http://backend:8000). Node resolves "localhost" to IPv6 first, uvicorn listens on IPv4.
const API_URL = (process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
  .replace(/\/$/, "")
  .replace("//localhost:", "//127.0.0.1:");

const nextConfig: NextConfig = {
  output: "standalone",
  // The demo sandbox cookie must be first-party, so sandbox calls go through this origin.
  async rewrites() {
    return [{ source: "/api/sandbox/:path*", destination: `${API_URL}/api/sandbox/:path*` }];
  },
};

export default nextConfig;
