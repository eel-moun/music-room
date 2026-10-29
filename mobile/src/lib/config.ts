// The backend address is configurable in the app (subject V.5): Settings screen.
import { load, save } from './storage';

// The PC's LAN IP, so a phone on the same Wi-Fi reaches the API. Overridable at
// build time (EXPO_PUBLIC_API_URL in mobile/.env) and at runtime (Settings).
export const DEFAULT_API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://192.168.1.10:8000';

let apiUrl = DEFAULT_API_URL;

export async function loadApiUrl(): Promise<string> {
  apiUrl = (await load('apiUrl')) ?? DEFAULT_API_URL;
  return apiUrl;
}

export function getApiUrl(): string {
  return apiUrl;
}

export async function setApiUrl(url: string): Promise<void> {
  apiUrl = url.trim().replace(/\/+$/, '');
  await save('apiUrl', apiUrl);
}
