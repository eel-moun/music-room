import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { Alert, Platform, useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '@/auth/AuthContext';
import { DeviceAgent } from '@/player/DeviceAgent';
import { useColors } from '@/ui/theme';

// react-native-web's Alert.alert does nothing: show errors with the browser's dialog.
if (Platform.OS === 'web') {
  Alert.alert = (title, message) => window.alert([title, message].filter(Boolean).join('\n\n'));
}

export default function RootLayout() {
  const scheme = useColorScheme();
  const c = useColors();
  return (
    <SafeAreaProvider>
      <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>
        <AuthProvider>
          <DeviceAgent>
            <Stack
              screenOptions={{
                headerBackButtonDisplayMode: 'minimal',
                headerStyle: { backgroundColor: c.bg },
                headerTintColor: c.text,
                headerTitleStyle: { color: c.text, fontWeight: '700' },
                headerShadowVisible: false,
                contentStyle: { backgroundColor: c.bg },
              }}
            >
              <Stack.Screen name="index" options={{ headerShown: false }} />
              <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
              <Stack.Screen name="login" options={{ title: 'Music Room' }} />
              <Stack.Screen name="register" options={{ title: 'Create an account' }} />
              <Stack.Screen name="forgot" options={{ title: 'Forgot password' }} />
              <Stack.Screen name="settings" options={{ title: 'Server settings' }} />
              <Stack.Screen name="event/new" options={{ title: 'New event' }} />
              <Stack.Screen name="event/[id]" options={{ title: 'Event' }} />
              <Stack.Screen name="playlist/new" options={{ title: 'New playlist' }} />
              <Stack.Screen name="playlist/[id]" options={{ title: 'Playlist' }} />
              <Stack.Screen name="device/[id]" options={{ title: 'Remote control' }} />
              <Stack.Screen name="user/[id]" options={{ title: 'Profile' }} />
            </Stack>
          </DeviceAgent>
        </AuthProvider>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
