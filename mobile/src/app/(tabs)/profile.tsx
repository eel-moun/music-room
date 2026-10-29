import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { del, patch, post } from '@/api/client';
import type { Me, ProfileUpdate } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { getGoogleIdToken, googleAvailable } from '@/auth/google';
import { alertError } from '@/lib/errors';
import { Body, Button, Card, Input, Label, Screen } from '@/ui/kit';

const list = (text: string) =>
  text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

export default function Profile() {
  const { me } = useAuth();
  // Remount the form when the saved profile changes, so it starts from fresh values.
  return me ? <ProfileForm key={JSON.stringify(me)} me={me} /> : null;
}

function ProfileForm({ me }: { me: Me }) {
  const { reloadMe, logout } = useAuth();
  const [form, setForm] = useState({
    display_name: me.display_name,
    bio: me.public_info.bio ?? '',
    first_name: me.friends_info?.first_name ?? '',
    last_name: me.friends_info?.last_name ?? '',
    city: me.friends_info?.city ?? '',
    phone: me.private_info?.phone ?? '',
    genres: (me.music_preferences.genres ?? []).join(', '),
    artists: (me.music_preferences.favorite_artists ?? []).join(', '),
  });
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    const body: ProfileUpdate = {
      display_name: form.display_name.trim(),
      public_info: { bio: form.bio, avatar_url: me.public_info.avatar_url ?? null },
      friends_info: {
        first_name: form.first_name || null,
        last_name: form.last_name || null,
        city: form.city || null,
      },
      private_info: { phone: form.phone || null, birth_date: me.private_info?.birth_date ?? null },
      music_preferences: { genres: list(form.genres), favorite_artists: list(form.artists) },
    };
    try {
      await patch('/users/me', body);
      await reloadMe();
      Alert.alert('Saved');
    } catch (e) {
      alertError(e);
    }
  };

  const linkGoogle = async () => {
    try {
      const idToken = await getGoogleIdToken();
      if (!idToken) return;
      await post('/auth/google/link', { id_token: idToken });
      await reloadMe();
    } catch (e) {
      alertError(e);
    }
  };

  const changePassword = async () => {
    try {
      await post('/auth/change-password', { current_password: current || null, new_password: next });
      setCurrent('');
      setNext('');
      await reloadMe();
      Alert.alert('Password changed');
    } catch (e) {
      alertError(e);
    }
  };

  return (
    <Screen>
      <Body muted>{me.email}</Body>
      <Card>
        <Label>Public (everyone)</Label>
        <Input label="Display name" value={form.display_name} onChangeText={set('display_name')} />
        <Input label="Bio" multiline value={form.bio} onChangeText={set('bio')} />
      </Card>
      <Card>
        <Label>Friends only</Label>
        <Input label="First name" value={form.first_name} onChangeText={set('first_name')} />
        <Input label="Last name" value={form.last_name} onChangeText={set('last_name')} />
        <Input label="City" value={form.city} onChangeText={set('city')} />
      </Card>
      <Card>
        <Label>Private (only you)</Label>
        <Input label="Phone" keyboardType="phone-pad" value={form.phone} onChangeText={set('phone')} />
      </Card>
      <Card>
        <Label>Music preferences (public)</Label>
        <Input label="Genres, comma separated" value={form.genres} onChangeText={set('genres')} />
        <Input label="Favorite artists, comma separated" value={form.artists} onChangeText={set('artists')} />
      </Card>
      <Button title="Save profile" onPress={save} />

      <Card>
        <Label>Google account</Label>
        <Body>{me.google_linked ? 'Linked' : 'Not linked'}</Body>
        {googleAvailable && !me.google_linked ? <Button title="Link Google" kind="secondary" onPress={linkGoogle} /> : null}
        {me.google_linked ? (
          <Button
            title="Unlink Google"
            kind="secondary"
            onPress={() => del('/auth/google/link').then(reloadMe).catch(alertError)}
          />
        ) : null}
        {!googleAvailable ? <Body muted>Linking Google needs the development build.</Body> : null}
      </Card>

      <Card>
        <Label>{me.has_password ? 'Change password' : 'Set a password'}</Label>
        {me.has_password ? (
          <Input label="Current password" secureTextEntry value={current} onChangeText={setCurrent} />
        ) : null}
        <Input label="New password" secureTextEntry value={next} onChangeText={setNext} />
        <Button title="Save password" kind="secondary" onPress={changePassword} />
      </Card>

      <Button title="Server settings" kind="secondary" onPress={() => router.push('/settings')} />
      <Button
        title="Log out"
        kind="danger"
        onPress={async () => {
          await logout();
          router.replace('/login');
        }}
      />
    </Screen>
  );
}
