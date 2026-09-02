/**
 * Subdomain helpers. `shop1.saas-pos.com` -> "shop1".
 *
 * The slug only tells the API which shop to *look up credentials in*; it never
 * grants access. Authorisation comes from the tenant id inside the JWT, and
 * the backend rejects a token whose shop does not match the host it arrived on.
 */
const RESERVED = new Set(["www", "api", "admin", "app", "static", "assets"]);

export function extractTenantSlug(
  host: string | null | undefined,
  baseDomain: string,
): string | null {
  if (!host) return null;
  const hostname = host.split(":")[0].toLowerCase().trim();
  const base = baseDomain.split(":")[0].toLowerCase().trim();

  if (!hostname || hostname === base || !hostname.endsWith(`.${base}`)) {
    return null;
  }

  const label = hostname.slice(0, -(base.length + 1));
  // Only a single leading label counts; deeper names are not tenants.
  if (!label || label.includes(".") || RESERVED.has(label)) return null;
  return label;
}

export function tenantUrl(slug: string, baseDomain: string): string {
  const protocol = baseDomain.startsWith("localhost") ? "http" : "https";
  return `${protocol}://${slug}.${baseDomain}`;
}
