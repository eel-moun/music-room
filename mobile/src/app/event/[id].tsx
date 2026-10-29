import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert } from 'react-native';

import { del, get, post } from '@/api/client';
import type { EventOut, FriendOut, Queue, Track, UserSummary } from '@/api/types';
import { HostPlayer } from '@/features/HostPlayer';
import { formatDuration, TrackSearch } from '@/features/TrackSearch';
import { alertError, message } from '@/lib/errors';
import { currentPosition } from '@/lib/location';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, ErrorText, Label, ListItem, Loading, Row, Screen } from '@/ui/kit';

export default function EventScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [event, setEvent] = useState<EventOut | null>(null);
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  useRoom(`event:${id}`, (msg) => {
    if (msg.type === 'queue.updated') applyQueue(msg.payload as Queue, false);
    else if (msg.type === 'event.deleted' || msg.type === 'access_revoked') {
      Alert.alert('This event is no longer available');
      router.back();
    } else load(); // resync, event.updated
  });

  // Location-licensed events need the phone's position with each vote.
  const position = async () => (event?.license === 'location_time' ? (await currentPosition()) ?? {} : {});

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

  if (!event || !queue) return error ? <ErrorText error={error} /> : <Loading />;

  return (
    <Screen onRefresh={load}>
      <Stack.Screen options={{ title: event.name }} />
      <Body muted>
        by {event.owner.display_name} · {event.visibility} · votes: {event.license.replace('_', ' + ')}
      </Body>
      {event.description ? <Body>{event.description}</Body> : null}
      <ErrorText error={error} />

      {event.is_owner ? <HostPlayer eventId={event.id} queue={queue} /> : null}
      {!event.is_owner && queue.now_playing ? (
        <Card>
          <Label>Now playing</Label>
          <Body>
            {queue.now_playing.title} · {queue.now_playing.artist}
          </Body>
        </Card>
      ) : null}

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

  const invitedIds = new Set(invited.map((u) => u.id));
  return (
    <Card>
      <Label>Invites</Label>
      {friends.length === 0 ? <Body muted>Add friends to invite them.</Body> : null}
      {friends.map(({ user }) => (
        <Row key={user.id}>
          <Body>{user.display_name}</Body>
          {invitedIds.has(user.id) ? (
            <Button
              title="Uninvite"
              small
              kind="danger"
              onPress={() => del(`/events/${eventId}/invites/${user.id}`).then(load).catch(alertError)}
            />
          ) : (
            <Button
              title="Invite"
              small
              kind="secondary"
              onPress={() => post(`/events/${eventId}/invites`, { user_id: user.id }).then(load).catch(alertError)}
            />
          )}
        </Row>
      ))}
    </Card>
  );
}
