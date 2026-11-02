// Tokens and per-install ids live in the OS keystore (Android Keystore / iOS Keychain),
// never in plain AsyncStorage: a backup or another app can't read them.
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEYS = {
  apiUrl: 'api_url',
  accessToken: 'access_token',
  refreshToken: 'refresh_token',
  deviceId: 'device_id',
} as const;

type Key = keyof typeof KEYS;

// The web preview has no keystore: it falls back to localStorage (readable by any script
// on the page, so acceptable for a local preview only, never for a real web app).
const web = Platform.OS === 'web';

export async function load(key: Key): Promise<string | null> {
  if (web) return localStorage.getItem(KEYS[key]);
  return SecureStore.getItemAsync(KEYS[key]);
}

export async function save(key: Key, value: string | null): Promise<void> {
  if (web) {
    if (value === null) localStorage.removeItem(KEYS[key]);
    else localStorage.setItem(KEYS[key], value);
    return;
  }
  if (value === null) await SecureStore.deleteItemAsync(KEYS[key]);
  else await SecureStore.setItemAsync(KEYS[key], value);
}
