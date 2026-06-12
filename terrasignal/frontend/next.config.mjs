/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The browser calls the backend directly via NEXT_PUBLIC_API_BASE (CORS), so
  // no dev proxy/rewrite is needed here.
};

export default nextConfig;
