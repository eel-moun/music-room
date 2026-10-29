import type { ConfigContext, ExpoConfig } from 'expo/config';

// Per-platform settings live here (CLAUDE.md: cross-platform code, per-platform config).
// Google Sign-In's iOS plugin needs the iOS client's reversed id; it's added only when
// set, so the app still builds (and runs in Expo Go) without Google configured.
const googleIosUrlScheme = process.env.GOOGLE_IOS_URL_SCHEME;

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: 'Music Room',
  slug: 'music-room',
  version: '1.0.0',
  orientation: 'portrait',
  icon: './assets/images/icon.png',
  scheme: 'musicroom',
  userInterfaceStyle: 'automatic',
  ios: {
    bundleIdentifier: 'com.musicroom.app',
    icon: './assets/expo.icon',
    infoPlist: {
      NSLocationWhenInUseUsageDescription:
        'Some events only accept votes from people at the venue. Your position is sent when you vote.',
      // The backend runs on the LAN over HTTP during development and the defense.
      NSAppTransportSecurity: { NSAllowsArbitraryLoads: true },
    },
  },
  android: {
    package: 'com.musicroom.app',
    adaptiveIcon: {
      backgroundColor: '#E6F4FE',
      foregroundImage: './assets/images/android-icon-foreground.png',
      backgroundImage: './assets/images/android-icon-background.png',
      monochromeImage: './assets/images/android-icon-monochrome.png',
    },
    permissions: ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION'],
    predictiveBackGestureEnabled: false,
  },
  web: {
    output: 'server',
    favicon: './assets/images/favicon.png',
  },
  plugins: [
    'expo-router',
    'expo-secure-store',
    ['expo-audio', { enableBackgroundPlayback: true }],
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'Some events only accept votes from people at the venue. Your position is sent when you vote.',
      },
    ],
    [
      'expo-splash-screen',
      { backgroundColor: '#208AEF', image: './assets/images/splash-icon.png', imageWidth: 76 },
    ],
    ...(googleIosUrlScheme
      ? [['@react-native-google-signin/google-signin', { iosUrlScheme: googleIosUrlScheme }] as [string, object]]
      : []),
  ],
  experiments: {
    reactCompiler: true,
  },
});
