export interface Role {
  id: number;
  name: string;
}

export interface User {
  id: number;
  email: string;
  is_admin: boolean;
  roles: Role[];
}

export interface DocumentInfo {
  id: number;
  title: string;
  filename: string;
  created_at: string;
  roles: Role[];
}

export interface Source {
  id: number;
  document_id: number;
  title: string;
  chunk_index: number;
  similarity: number;
}

export interface Answer {
  answer: string;
  refused: boolean;
  sources: Source[];
}

export interface LogEntry {
  id: number;
  user_id: number | null;
  user_email: string | null;
  question: string;
  retrieved_document_ids: number[];
  retrieved_titles: string[];
  refused: boolean;
  created_at: string;
}

export interface LogPage {
  total: number;
  items: LogEntry[];
}

const BASE = "/api";
const TOKEN_KEY = "rag.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  return fallback;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  const resp = await fetch(BASE + path, { method, headers, body: payload });
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    if (resp.status === 401 && token) onUnauthorized();
    throw new ApiError(resp.status, errorMessage(data, resp.statusText));
  }
  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string }>("POST", "/auth/login", { email, password }),
  register: (email: string, password: string) =>
    request<User>("POST", "/auth/register", { email, password }),
  me: () => request<User>("GET", "/me"),
  ask: (question: string) => request<Answer>("POST", "/ask", { question }),
  documents: () => request<DocumentInfo[]>("GET", "/documents"),
  uploadDocument: (form: FormData) => request<DocumentInfo>("POST", "/documents", form),
  setDocumentRoles: (id: number, roleIds: number[]) =>
    request<DocumentInfo>("PATCH", `/documents/${id}/roles`, { role_ids: roleIds }),
  deleteDocument: (id: number) => request<void>("DELETE", `/documents/${id}`),
  users: () => request<User[]>("GET", "/users"),
  setUserRoles: (id: number, roleIds: number[]) =>
    request<User>("PUT", `/users/${id}/roles`, { role_ids: roleIds }),
  roles: () => request<Role[]>("GET", "/roles"),
  createRole: (name: string) => request<Role>("POST", "/roles", { name }),
  logs: (limit: number, offset: number) =>
    request<LogPage>("GET", `/admin/logs?limit=${limit}&offset=${offset}`),
};
