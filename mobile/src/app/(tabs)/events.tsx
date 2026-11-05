import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { get } from '@/api/client';
import type { EventOut } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { message } from '@/lib/errors';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Choice, ErrorText, Input, ListItem, Screen } from '@/ui/kit';

export default function Events() {
  const { me } = useAuth();
  const [events, setEvents] = useState<EventOut[]>([]);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'all' | 'mine'>('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ mine: String(scope === 'mine') });
      if (query.trim()) params.set('q', query.trim());
      setEvents(await get<EventOut[]>(`/events?${params}`));
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

  // Live updates: instantly shows events when invited or uninvited without manual refresh
  useRoom(me ? `user:${me.id}` : null, (event) => {
    if (event.type.startsWith('event.') || event.type === 'resync') load();
  });

  return (
    <Screen refreshing={loading} onRefresh={load}>
      <Button title="New event" onPress={() => router.push('/event/new')} />
      <Input placeholder="Search events" value={query} onChangeText={setQuery} onSubmitEditing={load} returnKeyType="search" />
      <Choice
        value={scope}
        onChange={setScope}
        options={[
          { value: 'all', label: 'All visible' },
          { value: 'mine', label: 'Mine & invited' },
        ]}
      />
      <ErrorText error={error} />
      {events.length === 0 && !loading ? <Body muted>No event yet.</Body> : null}
      {events.map((e) => (
        <ListItem
          key={e.id}
          title={e.name}
          subtitle={`${e.owner.display_name} · ${e.visibility} · votes: ${e.license.replace('_', ' + ')}`}
          onPress={() => router.push({ pathname: '/event/[id]', params: { id: e.id } })}
        />
      ))}
    </Screen>
  );
}
