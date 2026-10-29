import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { get } from '@/api/client';
import type { Playlist } from '@/api/types';
import { message } from '@/lib/errors';
import { Body, Button, Choice, ErrorText, Input, ListItem, Screen } from '@/ui/kit';

export default function Playlists() {
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'all' | 'mine'>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ mine: String(scope === 'mine') });
      if (query.trim()) params.set('q', query.trim());
      setPlaylists(await get<Playlist[]>(`/playlists?${params}`));
      setError(null);
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }, [query, scope]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  return (
    <Screen refreshing={loading} onRefresh={load}>
      <Button title="New playlist" onPress={() => router.push('/playlist/new')} />
      <Input placeholder="Search playlists" value={query} onChangeText={setQuery} onSubmitEditing={load} returnKeyType="search" />
      <Choice
        value={scope}
        onChange={setScope}
        options={[
          { value: 'all', label: 'All visible' },
          { value: 'mine', label: 'Mine & invited' },
        ]}
      />
      <ErrorText error={error} />
      {playlists.length === 0 && !loading ? <Body muted>No playlist yet.</Body> : null}
      {playlists.map((p) => (
        <ListItem
          key={p.id}
          title={p.name}
          subtitle={`${p.owner.display_name} · ${p.visibility} · ${p.can_edit ? 'you can edit' : 'read only'}`}
          onPress={() => router.push({ pathname: '/playlist/[id]', params: { id: p.id } })}
        />
      ))}
    </Screen>
  );
}
