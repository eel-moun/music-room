// Thin REST client: base URL from Settings, device headers, bearer token,
// and one transparent refresh when the access token has expired.
import { getApiUrl } from '@/lib/config';
import { deviceHeaders } from '@/lib/device';
import { load, save } from '@/lib/storage';

import type { TokenPair } from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: Record<string, unknown>,
  ) {
    super(message);
  }
}

let onSessionExpired: () => void = () => {};
export function setSessionExpiredHandler(handler: () => void) {
  onSessionExpired = handler;
}

export async function storeTokens(tokens: TokenPair | null): Promise<void> {
  await save('accessToken', tokens?.access_token ?? null);
  await save('refreshToken', tokens?.refresh_token ?? null);
}

// One refresh at a time. The server rotates refresh tokens and treats a replayed
// one as theft (it revokes the session), so two parallel refreshes would log us out.
let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const refreshToken = await load('refreshToken');
  if (!refreshToken) return false;
  const response = await fetch(`${getApiUrl()}/auth/refresh`, {
    method: 'POST',
    headers: { ...deviceHeaders, 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) return false;
  await storeTokens(await response.json());
  return true;
}

function refreshOnce(): Promise<boolean> {
  refreshing ??= refreshTokens()
    .catch(() => false)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const token = await load('accessToken');
  return fetch(`${getApiUrl()}${path}`, {
    method,
    headers: {
      ...deviceHeaders,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

export async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await send(method, path, body);
    if (response.status === 401 && !path.startsWith('/auth/') && (await refreshOnce())) {
      response = await send(method, path, body);
    }
  } catch {
    throw new ApiError(0, 'network', `Can't reach the server at ${getApiUrl()}`);
  }

  if (response.status === 401 && !path.startsWith('/auth/')) onSessionExpired();
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw toError(response.status, data);
  return data as T;
}

function toError(status: number, data: unknown): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    return new ApiError(status, String(d.code ?? 'error'), String(d.message ?? d.code ?? 'Error'), d);
  }
  if (Array.isArray(detail)) {
    // FastAPI validation error: show the first message.
    const first = detail[0] as { msg?: string; loc?: string[] };
    const field = first?.loc?.slice(-1)[0];
    return new ApiError(status, 'validation', `${field ? `${field}: ` : ''}${first?.msg ?? 'Invalid input'}`);
  }
  return new ApiError(status, 'error', `Server error (${status})`);
}

export const get = <T>(path: string) => api<T>('GET', path);
export const post = <T>(path: string, body?: unknown) => api<T>('POST', path, body ?? {});
export const patch = <T>(path: string, body: unknown) => api<T>('PATCH', path, body);
export const put = <T>(path: string, body: unknown) => api<T>('PUT', path, body);
export const del = <T = void>(path: string) => api<T>('DELETE', path);
