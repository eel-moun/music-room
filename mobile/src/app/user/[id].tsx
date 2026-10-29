import { Stack, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert } from 'react-native';

import { get, post } from '@/api/client';
import type { Profile } from '@/api/types';
import { alertError, message } from '@/lib/errors';
import { Body, Button, Card, ErrorText, Label, Loading, Screen } from '@/ui/kit';

export default function UserProfile() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<Profile>(`/users/${id}`).then(setProfile).catch((e) => setError(message(e)));
  }, [id]);

  if (!profile) return error ? <ErrorText error={error} /> : <Loading />;
  const prefs = profile.music_preferences;

  return (
    <Screen>
      <Stack.Screen options={{ title: profile.display_name }} />
      <Card>
        <Label>About</Label>
        <Body>{profile.public_info.bio || 'No bio.'}</Body>
      </Card>
      <Card>
        <Label>Music</Label>
        <Body>Genres: {prefs.genres?.length ? prefs.genres.join(', ') : '—'}</Body>
        <Body>Artists: {prefs.favorite_artists?.length ? prefs.favorite_artists.join(', ') : '—'}</Body>
      </Card>
      {profile.friends_info ? (
        <Card>
          <Label>Friends only</Label>
          <Body>
            {[profile.friends_info.first_name, profile.friends_info.last_name].filter(Boolean).join(' ') || '—'}
          </Body>
          {profile.friends_info.city ? <Body muted>{profile.friends_info.city}</Body> : null}
        </Card>
      ) : (
        <Body muted>More details are visible to friends only.</Body>
      )}
      {profile.relation === 'other' ? (
        <Button
          title="Add friend"
          onPress={() =>
            post('/friends/requests', { user_id: profile.id })
              .then(() => Alert.alert('Friend request sent'))
              .catch(alertError)
          }
        />
      ) : null}
    </Screen>
  );
}
