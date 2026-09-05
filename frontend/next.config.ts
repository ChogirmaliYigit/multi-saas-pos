import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits a self-contained server bundle with only the node_modules actually
  // imported, so the same codebase can be self-hosted from the compose file
  // without shipping a 400MB node_modules.
  //
  // Off on Vercel. Vercel builds its own output format, and standalone
  // redirects the build into .next/standalone where its pipeline does not
  // look -- the build compiles, reports success, and produces a deployment
  // with nothing in it. Every host then answers DEPLOYMENT_NOT_FOUND, which
  // reads like a domain problem rather than a build one.
  output: process.env.VERCEL ? undefined : "standalone",
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
