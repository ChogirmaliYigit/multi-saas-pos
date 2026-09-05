/**
 * Mirrors the FastAPI schemas. Enum values are the backend's *values*
 * (lowercase), not its Python member names -- the API serialises
 * UserRole.OWNER as "owner".
 */

export type UserRole = "super_admin" | "owner" | "manager" | "cashier";

export type TenantStatus = "trial" | "active" | "suspended" | "cancelled";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  tenant_id: string | null;
  branch_id: string | null;
  phone: string | null;
  avatar_url: string | null;
  is_active: boolean;
}

export interface SessionInfo {
  user: UserPublic;
  tenant_slug: string | null;
  /** Exactly what the API will allow. The UI hides what this omits. */
  permissions: string[];
}

export interface TerminalStaff {
  id: string;
  full_name: string;
  role: UserRole;
  avatar_url: string | null;
  has_pin: boolean;
}

/** The error envelope every API failure uses. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: Record<string, unknown>;
  request_id: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}
