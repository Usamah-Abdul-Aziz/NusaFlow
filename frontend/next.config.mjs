/** @type {import('next').NextConfig} */

// This file runs on the Next.js server/build, not in the browser, so a
// plain (non NEXT_PUBLIC_) env var is fine here and won't be exposed to
// the client. Falls back to localhost for local dev so `next dev` keeps
// working with zero config.
//
// Previously this was hardcoded to 'http://localhost:8000', which meant
// the rewrite would silently break on any deployment (e.g. Vercel) where
// the backend isn't reachable at localhost. Set BACKEND_URL in the
// environment (Vercel dashboard, or .env for local) to point at the real
// backend host once one exists.
const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';

const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
