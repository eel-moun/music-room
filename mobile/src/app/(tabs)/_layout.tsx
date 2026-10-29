import { Redirect } from 'expo-router';
import { Tabs } from 'expo-router/js-tabs';
import { Text, type ColorValue } from 'react-native';

import { useAuth } from '@/auth/AuthContext';

const icon = (glyph: string) =>
  function TabIcon({ color }: { color: ColorValue }) {
    return <Text style={{ color, fontSize: 18 }}>{glyph}</Text>;
  };

export default function TabsLayout() {
  const { me, ready } = useAuth();
  if (ready && !me) return <Redirect href="/login" />;
  return (
    <Tabs>
      <Tabs.Screen name="events" options={{ title: 'Track Vote', tabBarIcon: icon('♫') }} />
      <Tabs.Screen name="playlists" options={{ title: 'Playlists', tabBarIcon: icon('≡') }} />
      <Tabs.Screen name="devices" options={{ title: 'Devices', tabBarIcon: icon('◉') }} />
      <Tabs.Screen name="friends" options={{ title: 'Friends', tabBarIcon: icon('☺') }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile', tabBarIcon: icon('⚙') }} />
    </Tabs>
  );
}
