import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Application de bureau (deploy/desktop) : le site est livré en « standalone », un dossier
  // autonome lancé par `node server.js` avec le Node.js embarqué. Hors de ce cas, rien ne change.
  ...(process.env.TMS_STANDALONE === "1"
    ? { output: "standalone" as const, outputFileTracingRoot: process.cwd() }
    : {}),
};

export default nextConfig;
