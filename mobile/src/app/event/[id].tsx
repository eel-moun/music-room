import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Platform } from 'react-native';

import { del, get, post } from '@/api/client';
import type { EventOut, FriendOut, Queue, Track, UserSummary } from '@/api/types';
import { GuestPlayer, HostPlayer } from '@/features/HostPlayer';
import { formatDuration, TrackSearch } from '@/features/TrackSearch';
import { alertError, message } from '@/lib/errors';
import { currentPosition } from '@/lib/location';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, ErrorText, Input, Label, ListItem, Loading, Row, Screen } from '@/ui/kit';

export default function EventScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [event, setEvent] = useState<EventOut | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [simLocation, setSimLocation] = useState<'inside' | 'outside'>('inside');
  // Pushes are shared by all viewers, so they don't say what *I* voted: keep it here.
  const myVotes = useRef(new Set<string>());

  const applyQueue = useCallback((q: Queue, fromServerForMe: boolean) => {
    if (fromServerForMe) {
      myVotes.current = new Set(q.queue.filter((t) => t.voted_by_me).map((t) => t.id));
    }
    setQueue({
      ...q,
      queue: q.queue.map((t) => ({ ...t, voted_by_me: myVotes.current.has(t.id) })),
    });
  }, []);

  const load = useCallback(async () => {
    try {
      const [e, q] = await Promise.all([get<EventOut>(`/events/${id}`), get<Queue>(`/events/${id}/queue`)]);
      setEvent(e);
      applyQueue(q, true);
      setError(null);
    } catch (e) {
      setError(message(e));
    }
  }, [id, applyQueue]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const goBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/(tabs)/events');
    }
  };

  useRoom(`event:${id}`, (msg) => {
    if (msg.type === 'queue.updated') applyQueue(msg.payload as Queue, false);
    else if (msg.type === 'event.deleted' || msg.type === 'access_revoked') {
      Alert.alert('This event is no longer available');
      goBack();
    } else load(); // resync, event.updated
  });

  // Location-licensed events need the phone's position with each vote.
  const position = async () => {
    if (event?.license !== 'location_time') return {};
    if (simLocation === 'outside' && event.latitude != null && event.longitude != null) {
      // Simulate ~111km away to test geofence rejection
      return { latitude: event.latitude + 1.0, longitude: event.longitude + 1.0 };
    }
    const pos = await currentPosition();
    if (pos) return pos;
    // Browser fallback: if GPS is blocked on HTTP origins, assume user is at the venue
    if (event.latitude != null && event.longitude != null) {
      return { latitude: event.latitude, longitude: event.longitude };
    }
    return {};
  };

  const toggleVote = async (trackId: string, voted: boolean) => {
    try {
      const q = voted
        ? await del<Queue>(`/events/${id}/tracks/${trackId}/vote`)
        : await post<Queue>(`/events/${id}/tracks/${trackId}/vote`, await position());
      applyQueue(q, true);
    } catch (e) {
      alertError(e, "Can't vote");
    }
  };

  const suggest = async (track: Track) => {
    const q = await post<Queue>(`/events/${id}/tracks`, {
      provider: track.provider,
      external_id: track.external_id,
      ...(await position()),
    });
    applyQueue(q, true);
  };

  if (!event || !queue) {
    return (
      <Screen onRefresh={load}>
        <Stack.Screen
          options={{
            title: 'Event',
            headerLeft: Platform.OS === 'web' ? () => <Button title="← Back" small kind="secondary" onPress={goBack} /> : undefined,
          }}
        />
        {error ? (
          <Card>
            <ErrorText error={error} />
            <Button title="← Back to events" kind="secondary" onPress={goBack} />
          </Card>
        ) : (
          <Loading />
        )}
      </Screen>
    );
  }

  return (
    <Screen onRefresh={load}>
      <Stack.Screen
        options={{
          title: event.name,
          headerLeft: Platform.OS === 'web' ? () => <Button title="← Back" small kind="secondary" onPress={goBack} /> : undefined,
        }}
      />
      <Body muted>
        by {event.owner.display_name} · {event.visibility} · votes: {event.license.replace('_', ' + ')}
      </Body>
      {event.description ? <Body>{event.description}</Body> : null}
      <ErrorText error={error} />

      {event.license === 'location_time' ? (
        <Card>
          <Label>📍 Location & Time license active</Label>
          <Body muted>
            Venue: {event.latitude?.toFixed(4)}, {event.longitude?.toFixed(4)} (Radius: {event.radius_m}m)
          </Body>
          <Row>
            <Button
              title="📍 Inside venue"
              small
              kind={simLocation === 'inside' ? 'primary' : 'secondary'}
              onPress={() => setSimLocation('inside')}
            />
            <Button
              title="🌍 Simulate 100km away (Outside)"
              small
              kind={simLocation === 'outside' ? 'danger' : 'secondary'}
              onPress={() => setSimLocation('outside')}
            />
          </Row>
          {simLocation === 'outside' ? (
            <Body muted>Next vote will be sent from ~100km away to demonstrate geofence rejection.</Body>
          ) : null}
        </Card>
      ) : null}

      {event.is_owner ? (
        <HostPlayer eventId={event.id} queue={queue} />
      ) : (
        <GuestPlayer queue={queue} />
      )}

      <Label>Up next (most votes first)</Label>
      {queue.queue.length === 0 ? <Body muted>The queue is empty: suggest a track below.</Body> : null}
      {queue.queue.map((t, index) => (
        <ListItem
          key={t.id}
          title={`${index + 1}. ${t.title}`}
          subtitle={`${t.artist} · ${formatDuration(t.duration)} · ${t.votes} vote${t.votes === 1 ? '' : 's'}`}
          right={
            <Button
              title={t.voted_by_me ? '♥ Voted' : '♡ Vote'}
              small
              kind={t.voted_by_me ? 'primary' : 'secondary'}
              onPress={() => toggleVote(t.id, !!t.voted_by_me)}
            />
          }
        />
      ))}

      <Card>
        <Label>Suggest a track</Label>
        <TrackSearch actionLabel="Suggest" onPick={suggest} />
      </Card>

      {event.is_owner ? <Invites eventId={event.id} /> : null}
    </Screen>
  );
}

function Invites({ eventId }: { eventId: string }) {
  const [invited, setInvited] = useState<UserSummary[]>([]);
  const [friends, setFriends] = useState<FriendOut[]>([]);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSummary[]>([]);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    const [i, f] = await Promise.all([
      get<UserSummary[]>(`/events/${eventId}/invites`),
      get<FriendOut[]>('/friends'),
    ]);
    setInvited(i);
    setFriends(f);
  }, [eventId]);

  useFocusEffect(
    useCallback(() => {
      load().catch(alertError);
    }, [load]),
  );

  const search = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await get<UserSummary[]>(`/users?q=${encodeURIComponent(query.trim())}`);
      setSearchResults(res);
    } catch (e) {
      alertError(e);
    } finally {
      setSearching(false);
    }
  };

  const inviteUser = async (userId: string) => {
    try {
      await post(`/events/${eventId}/invites`, { user_id: userId });
      await load();
    } catch (e) {
      alertError(e);
    }
  };

  const uninviteUser = async (userId: string) => {
    try {
      await del(`/events/${eventId}/invites/${userId}`);
      await load();
    } catch (e) {
      alertError(e);
    }
  };

  const invitedIds = new Set(invited.map((u) => u.id));

  return (
    <Card>
      <Label>Invited guests ({invited.length})</Label>
      {invited.length === 0 ? <Body muted>No one invited yet.</Body> : null}
      {invited.map((u) => (
        <Row key={u.id}>
          <Body>{u.display_name}</Body>
          <Button
            title="Uninvite"
            small
            kind="danger"
            onPress={() => uninviteUser(u.id)}
          />
        </Row>
      ))}

      <Label>Invite anyone by display name</Label>
      <Row>
        <Input
          placeholder="Display name..."
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={search}
        />
        <Button title="Search" small onPress={search} busy={searching} />
      </Row>

      {searchResults.length > 0 ? (
        <>
          <Label>Search results</Label>
          {searchResults.map((u) => (
            <Row key={u.id}>
              <Body>{u.display_name}</Body>
              {invitedIds.has(u.id) ? (
                <Button title="Uninvite" small kind="danger" onPress={() => uninviteUser(u.id)} />
              ) : (
                <Button title="Invite" small kind="secondary" onPress={() => inviteUser(u.id)} />
              )}
            </Row>
          ))}
        </>
      ) : null}

      {friends.length > 0 ? (
        <>
          <Label>Quick invite friends</Label>
          {friends.map(({ user }) => (
            <Row key={user.id}>
              <Body>{user.display_name}</Body>
              {invitedIds.has(user.id) ? (
                <Button
                  title="Uninvite"
                  small
                  kind="danger"
                  onPress={() => uninviteUser(user.id)}
                />
              ) : (
                <Button
                  title="Invite"
                  small
                  kind="secondary"
                  onPress={() => inviteUser(user.id)}
                />
              )}
            </Row>
          ))}
        </>
      ) : null}
    </Card>
  );
}
