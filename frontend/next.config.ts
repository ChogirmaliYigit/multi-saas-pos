import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle with only the node_modules actually
  // imported. Vercel ignores this; it exists so the same codebase can be
  // self-hosted from the compose file without shipping a 400MB node_modules.
  output: "standalone",
  // The backend, not Next, is the API. Keeping the build free of server-only
  // node deps keeps the Vercel deploy small.
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            // usb/bluetooth stay open: Step 4 drives thermal printers through
            // WebUSB and Web Bluetooth from this origin.
            value: "camera=(self), microphone=(), geolocation=(), usb=(self), bluetooth=(self)",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
