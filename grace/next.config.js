/** @type {import('next').NextConfig} */
const nextConfig = {
  // libsodium-wrappers' ESM build confuses webpack's bundler (looks for a
  // sibling file that only exists in the CJS build) — keep it external so
  // Next just requires it at runtime via Node instead of bundling it.
  experimental: {
    serverComponentsExternalPackages: ["libsodium-wrappers"],
  },
};
module.exports = nextConfig;
