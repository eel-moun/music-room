import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useColorScheme } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { AuthProvider } from '@/auth/AuthContext';
import { DeviceAgent } from '@/player/DeviceAgent';

export default function RootLayout() {
  const scheme = useColorScheme();
  return (
    <SafeAreaProvider>
      <ThemeProvider value={scheme === 'dark' ? DarkTheme : DefaultTheme}>
        <AuthProvider>
          <DeviceAgent>
            <Stack screenOptions={{ headerBackButtonDisplayMode: 'minimal' }}>
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
