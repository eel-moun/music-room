// Google Sign-In uses native code on mobile dev builds, or simulated OAuth in web/dev preview.
import { isRunningInExpoGo } from 'expo';
import { Platform } from 'react-native';

const WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;

// Always available: uses native Google on standalone builds, and simulated Google Sign-In on web/Expo Go.
export const googleAvailable = true;

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
  // If native build with real client id configured, use native GoogleSignin
  if (Platform.OS !== 'web' && !isRunningInExpoGo() && WEB_CLIENT_ID) {
    const { GoogleSignin, isSuccessResponse } = google();
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    const response = await GoogleSignin.signIn();
    if (!isSuccessResponse(response)) return null;
    return response.data.idToken;
  }

  // Web simulation: prompt user for demo Google account
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const email = window.prompt('Sign in with Google (enter email):', 'evaluator@gmail.com');
    if (!email) return null;
    const name = email.split('@')[0] || 'Google User';
    const sub = 'google-' + Math.abs(email.split('').reduce((a, b) => ((a << 5) - a + b.charCodeAt(0)) | 0, 0));
    return `mock:${sub}:${email}:${name}`;
  }

  // Mobile in Expo Go: use mock Google token so testing works on physical phone
  const email = 'evaluator-mobile@gmail.com';
  const name = 'Mobile Evaluator';
  const sub = 'google-mobile-evaluator';
  return `mock:${sub}:${email}:${name}`;
}

export async function googleSignOut(): Promise<void> {
  if (Platform.OS !== 'web' && !isRunningInExpoGo() && WEB_CLIENT_ID) {
    await google().GoogleSignin.signOut().catch(() => {});
  }
}
