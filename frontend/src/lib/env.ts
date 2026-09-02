/**
 * Environment access in one place, so a missing variable fails loudly at
 * module load rather than as a confusing "fetch failed" at runtime.
 *
 * NEXT_PUBLIC_* values are inlined into the client bundle at build time, so
 * they must never hold anything secret.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing environment variable ${name}. Copy .env.local.example to .env.local.`,
    );
  }
  return value;
}

export const env = {
  /** Public FastAPI base URL, e.g. https://api.saas-pos.com */
  apiUrl: required(
    "NEXT_PUBLIC_API_URL",
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  ).replace(/\/$/, ""),

  /** Root domain used to derive tenant subdomains: shop1.<baseDomain> */
  baseDomain: process.env.NEXT_PUBLIC_BASE_DOMAIN ?? "localhost:3000",

  /** Server-only. Falls back to the public URL for local single-host setups. */
  internalApiUrl: (
    process.env.INTERNAL_API_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000"
  ).replace(/\/$/, ""),

  isProduction: process.env.NODE_ENV === "production",
} as const;

export const API_V1 = "/api/v1";
