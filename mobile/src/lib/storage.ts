// Tokens and per-install ids live in the OS keystore (Android Keystore / iOS Keychain),
// never in plain AsyncStorage: a backup or another app can't read them.
import * as SecureStore from 'expo-secure-store';

const KEYS = {
  apiUrl: 'api_url',
  accessToken: 'access_token',
  refreshToken: 'refresh_token',
  deviceId: 'device_id',
} as const;

type Key = keyof typeof KEYS;

export async function load(key: Key): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS[key]);
}

export async function save(key: Key, value: string | null): Promise<void> {
  if (value === null) await SecureStore.deleteItemAsync(KEYS[key]);
  else await SecureStore.setItemAsync(KEYS[key], value);
}
