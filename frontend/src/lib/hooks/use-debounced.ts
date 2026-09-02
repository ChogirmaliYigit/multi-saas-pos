"use client";

import { useEffect, useState } from "react";

/**
 * Delay a rapidly-changing value.
 *
 * Search boxes fire a query per keystroke otherwise; on a catalog of ten
 * thousand products that is a request every 40ms, and the results flicker
 * between prefixes as they race.
 */
export function useDebounced<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
