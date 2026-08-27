/**
 * Where the build output goes, and why it is not always `.next`.
 *
 * `next dev` and `next build` write different things into the same directory, and a dev
 * server sharing `.next` with a production build leaves the two interleaved. The symptom
 * is not a clear error: it is `__webpack_modules__[moduleId] is not a function` thrown out
 * of `.next/server/pages/_document.js`, or a route that answers 404 because the manifest
 * on disk describes the other build. Both look like application bugs and are not.
 *
 * So anything that starts a server of its own — the browser check in tools/browser — sets
 * this to its own directory and stays out of the way of whatever the developer is running.
 */
const distDir = process.env.AEGIS_DIST_DIR?.trim() || '.next';

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir,
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
        ],
      },
    ];
  },
};
export default nextConfig;
