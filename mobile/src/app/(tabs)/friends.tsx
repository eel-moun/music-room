import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { del, get, post } from '@/api/client';
import type { FriendOut, FriendRequest, UserSummary } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { alertError, message } from '@/lib/errors';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, ErrorText, Input, Label, ListItem, Row, Screen } from '@/ui/kit';

export default function Friends() {
  const { me } = useAuth();
  const [friends, setFriends] = useState<FriendOut[]>([]);
  const [requests, setRequests] = useState<FriendRequest[]>([]);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<UserSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, r] = await Promise.all([get<FriendOut[]>('/friends'), get<FriendRequest[]>('/friends/requests')]);
      setFriends(f);
      setRequests(r);
      setError(null);
    } catch (e) {
      setError(message(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );
  // Live: someone sent or accepted a request.
  useRoom(me ? `user:${me.id}` : null, (event) => {
    if (event.type.startsWith('friend.') || event.type === 'resync') load();
  });

  const search = async () => {
    try {
      setFound(await get<UserSummary[]>(`/users?q=${encodeURIComponent(query.trim())}`));
    } catch (e) {
      setError(message(e));
    }
  };

  const act = (action: () => Promise<unknown>) => () => action().then(load).catch(alertError);

  return (
    <Screen onRefresh={load}>
      <Card>
        <Label>Find people</Label>
        <Row>
          <Input style={{ minWidth: 200 }} placeholder="Display name" value={query} onChangeText={setQuery} onSubmitEditing={search} />
          <Button title="Search" small onPress={search} />
        </Row>
        {found.map((u) => (
          <ListItem
            key={u.id}
            title={u.display_name}
            onPress={() => router.push({ pathname: '/user/[id]', params: { id: u.id } })}
            right={<Button title="Add" small kind="secondary" onPress={act(() => post('/friends/requests', { user_id: u.id }))} />}
          />
        ))}
      </Card>
      <ErrorText error={error} />

      {requests.length ? <Label>Requests</Label> : null}
      {requests.map((r) => (
        <ListItem
          key={r.id}
          title={r.user.display_name}
          subtitle={r.direction === 'incoming' ? 'wants to be your friend' : 'request sent'}
          right={
            <Row>
              {r.direction === 'incoming' ? (
                <Button title="Accept" small onPress={act(() => post(`/friends/requests/${r.id}/accept`))} />
              ) : null}
              <Button
                title={r.direction === 'incoming' ? 'Decline' : 'Cancel'}
                small
                kind="secondary"
                onPress={act(() => del(`/friends/requests/${r.id}`))}
              />
            </Row>
          }
        />
      ))}

      <Label>Friends</Label>
      {friends.length === 0 ? <Body muted>No friends yet. Search for someone above.</Body> : null}
      {friends.map((f) => (
        <ListItem
          key={f.user.id}
          title={f.user.display_name}
          onPress={() => router.push({ pathname: '/user/[id]', params: { id: f.user.id } })}
          right={<Button title="Remove" small kind="danger" onPress={act(() => del(`/friends/${f.user.id}`))} />}
        />
      ))}
    </Screen>
  );
}
