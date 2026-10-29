// Google Sign-In uses native code that Expo Go doesn't contain. It's loaded only in a
// development build; in Expo Go the Google button is hidden (email login still works).
import { isRunningInExpoGo } from 'expo';

const WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;

export const googleAvailable = !isRunningInExpoGo() && !!WEB_CLIENT_ID;

type GoogleModule = typeof import('@react-native-google-signin/google-signin');
let module: GoogleModule | null = null;

function google(): GoogleModule {
  if (!module) {
    // Loaded lazily on purpose: a static import would crash Expo Go at startup.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    module = require('@react-native-google-signin/google-signin') as GoogleModule;
    // webClientId = our backend's client id: the ID token's audience the server checks.
    module.GoogleSignin.configure({ webClientId: WEB_CLIENT_ID });
  }
  return module;
}

/** Opens Google's account picker; returns an ID token for the backend, or null if cancelled. */
export async function getGoogleIdToken(): Promise<string | null> {
  const { GoogleSignin, isSuccessResponse } = google();
  await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
  const response = await GoogleSignin.signIn();
  if (!isSuccessResponse(response)) return null;
  return response.data.idToken;
}

export async function googleSignOut(): Promise<void> {
  if (googleAvailable) await google().GoogleSignin.signOut().catch(() => {});
}
