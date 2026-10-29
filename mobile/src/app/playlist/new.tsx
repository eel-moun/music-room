import { router } from 'expo-router';
import { useState } from 'react';

import { post } from '@/api/client';
import type { Playlist } from '@/api/types';
import { message } from '@/lib/errors';
import { Button, Card, Choice, ErrorText, Input, Screen } from '@/ui/kit';

export default function NewPlaylist() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<Playlist['visibility']>('public');
  const [license, setLicense] = useState<Playlist['license']>('everyone');
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    try {
      const playlist = await post<Playlist>('/playlists', { name: name.trim(), description, visibility, license });
      router.replace({ pathname: '/playlist/[id]', params: { id: playlist.id } });
    } catch (e) {
      setError(message(e));
    }
  };

  return (
    <Screen>
      <Card>
        <Input label="Name" value={name} onChangeText={setName} autoCapitalize="sentences" />
        <Input label="Description" value={description} onChangeText={setDescription} multiline />
        <Choice
          label="Who can see it"
          value={visibility}
          onChange={setVisibility}
          options={[
            { value: 'public', label: 'Everyone' },
            { value: 'private', label: 'Invited only' },
          ]}
        />
        <Choice
          label="Who can edit"
          value={license}
          onChange={setLicense}
          options={[
            { value: 'everyone', label: 'Everyone who sees it' },
            { value: 'invited', label: 'Invited only' },
          ]}
        />
      </Card>
      <ErrorText error={error} />
      <Button title="Create playlist" onPress={create} />
    </Screen>
  );
}
