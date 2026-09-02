import type { ApiErrorBody } from "./types";

/**
 * Carries the backend's stable `code` so callers branch on that rather than
 * string-matching human-facing copy (which changes, and is translated).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(status: number, body: Partial<ApiErrorBody>) {
    super(body.message ?? "Something went wrong.");
    this.name = "ApiError";
    this.status = status;
    this.code = body.code ?? "unknown_error";
    this.details = body.details ?? {};
    this.requestId = body.request_id ?? null;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  /** Shop suspended, or the plan does not cover this action. */
  get isBillingBlock(): boolean {
    return (
      this.status === 402 ||
      this.code === "tenant_inactive" ||
      this.code === "quota_exceeded"
    );
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
