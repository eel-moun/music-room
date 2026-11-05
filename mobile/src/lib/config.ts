// The backend address is configurable in the app (subject V.5): Settings screen.
import { Platform } from 'react-native';

import { load, save } from './storage';

// The PC's LAN IP, so a phone on the same Wi-Fi reaches the API. Overridable at
// build time (EXPO_PUBLIC_API_URL in mobile/.env) and at runtime (Settings).
function defaultApiUrl(): string {
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location.hostname && window.location.hostname !== 'localhost') {
    return `http://${window.location.hostname}:8000`;
  }
  if (process.env.EXPO_PUBLIC_API_URL) {
    return process.env.EXPO_PUBLIC_API_URL;
  }
  return 'http://localhost:8000';
}

export const DEFAULT_API_URL = defaultApiUrl();

let apiUrl = DEFAULT_API_URL;

export async function loadApiUrl(): Promise<string> {
  const saved = await load('apiUrl');
  if (saved) {
    // If on web and not on localhost, but storage has localhost, auto-migrate to the actual host
    if (
      Platform.OS === 'web' &&
      typeof window !== 'undefined' &&
      window.location.hostname &&
      window.location.hostname !== 'localhost' &&
      saved.includes('localhost')
    ) {
      apiUrl = `http://${window.location.hostname}:8000`;
      await save('apiUrl', apiUrl);
      return apiUrl;
    }
    apiUrl = saved;
    return apiUrl;
  }
  apiUrl = DEFAULT_API_URL;
  return apiUrl;
}

export function getApiUrl(): string {
  if (
    Platform.OS === 'web' &&
    typeof window !== 'undefined' &&
    window.location.hostname &&
    window.location.hostname !== 'localhost' &&
    apiUrl.includes('localhost')
  ) {
    return `http://${window.location.hostname}:8000`;
  }
  return apiUrl;
}

export async function setApiUrl(url: string): Promise<void> {
  apiUrl = url.trim().replace(/\/+$/, '');
  await save('apiUrl', apiUrl);
}
