import type { NextConfig } from "next";

// The browser only ever talks to /api on the same origin; requests are proxied
// server-side to the FastAPI backend, so no backend URL or secret reaches the client.
const API_URL = process.env.RISKPILOT_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
