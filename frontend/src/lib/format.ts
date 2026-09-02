/**
 * Formatting helpers. Money is always formatted from a string or number that
 * came off the API as a decimal -- never from arithmetic done in JavaScript
 * floats, which is why cart maths belongs on the server or in integer cents.
 */

export function formatMoney(
  amount: number | string,
  currency = "USD",
  locale = "en-US",
): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
  }).format(Number.isFinite(value) ? value : 0);
}

export function formatNumber(value: number | string, locale = "en-US"): string {
  const n = typeof value === "string" ? Number(value) : value;
  return new Intl.NumberFormat(locale).format(Number.isFinite(n) ? n : 0);
}

export function formatDate(
  value: string | Date,
  locale = "en-US",
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat(locale, options).format(date);
}

export function formatDateTime(value: string | Date, locale = "en-US"): string {
  return formatDate(value, locale, { dateStyle: "medium", timeStyle: "short" });
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
