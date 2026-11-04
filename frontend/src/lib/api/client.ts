/** Same-origin transport. Operator credentials are never compiled into a bundle. */
export const API_BASE_URL = "/api/control";
const TOKEN_KEY = "lattice.operator.session";
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return sessionStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}
export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem("Lattice_auth_token");
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}
export function errorMessage(body: unknown, status: number): string {
  const detail =
    body && typeof body === "object" && "detail" in body ? body.detail : null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc)
          ? item.loc.filter((x: unknown) => x !== "body").join(".")
          : "Request";
        return `${field}: ${typeof item.msg === "string" ? item.msg : item.type || "invalid value"}`;
      })
      .join("; ");
  return status === 401
    ? "Operator authorization expired or was rejected. Sign in again."
    : `Controller request failed (HTTP ${status}).`;
}
export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  if (
    !endpoint.startsWith("/") ||
    endpoint.startsWith("//") ||
    endpoint.includes("://")
  )
    throw new ApiError(400, "Use a controller API path.");
  const headers = new Headers(options.headers);
  const token = getAuthToken();
  if (token && !headers.has("Authorization"))
    headers.set("Authorization", `Bearer ${token}`);
  if (endpoint !== "/health" && !headers.has("Authorization"))
    throw new ApiError(
      401,
      "Connect an operator session before making changes.",
    );
  if (options.body) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(API_BASE_URL + endpoint, {
      ...options,
      headers,
      cache: "no-store",
      credentials: "omit",
      signal: options.signal || AbortSignal.timeout(30000),
    });
  } catch {
    throw new ApiError(
      0,
      "Controller unavailable. Check its server, tunnel and network, then retry.",
    );
  }
  if (response.status === 204) return undefined as T;
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      response.status || 502,
      "Controller returned an unreadable response.",
    );
  }
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined" && token)
      window.dispatchEvent(new Event("lattice:unauthorized"));
    throw new ApiError(response.status, errorMessage(data, response.status));
  }
  return data as T;
}
export async function verifyOperator(token: string) {
  if (!token.trim())
    throw new ApiError(401, "Enter your management bearer token.");
  await apiClient("/api/pools", {
    headers: { Authorization: `Bearer ${token.trim()}` },
  });
}
