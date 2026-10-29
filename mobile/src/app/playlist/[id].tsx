import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert } from 'react-native';

import { ApiError, del, get, post } from '@/api/client';
import type { FriendOut, PlaylistDetail, Track, UserSummary } from '@/api/types';
import { formatDuration, TrackSearch } from '@/features/TrackSearch';
import { alertError, message } from '@/lib/errors';
import { useDeviceAgent } from '@/player/DeviceAgent';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, ErrorText, Label, ListItem, Loading, Row, Screen } from '@/ui/kit';

export default function PlaylistScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { deviceId } = useDeviceAgent();
  const [playlist, setPlaylist] = useState<PlaylistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<PlaylistDetail | null>(null);

  const show = useCallback((p: PlaylistDetail) => {
    latest.current = p;
    setPlaylist(p);
  }, []);

  const load = useCallback(async () => {
    try {
      show(await get<PlaylistDetail>(`/playlists/${id}`));
      setError(null);
    } catch (e) {
      setError(message(e));
    }
  }, [id, show]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  useRoom(`playlist:${id}`, (msg) => {
    if (msg.type === 'playlist.updated') {
      // Someone (maybe us) changed it: adopt the server's state and version.
      const current = latest.current;
      if (current) show({ ...current, ...msg.payload, can_edit: current.can_edit });
    } else if (msg.type === 'playlist.deleted' || msg.type === 'access_revoked') {
      Alert.alert('This playlist is no longer available');
      router.back();
    } else load();
  });

  /**
   * Every change sends the version we saw. On 409 someone changed the playlist first:
   * refetch, then re-apply the same intent once if it still makes sense; otherwise
   * tell the user. Never overwrite blindly (ADR-007).
   */
  const edit = async (request: (version: number) => Promise<PlaylistDetail>, stillValid: (p: PlaylistDetail) => boolean) => {
    if (!latest.current) return;
    try {
      show(await request(latest.current.version));
    } catch (e) {
      if (!(e instanceof ApiError && e.code === 'version_conflict')) return alertError(e);
      const fresh = await get<PlaylistDetail>(`/playlists/${id}`);
      show(fresh);
      if (!stillValid(fresh)) {
        return Alert.alert('Playlist changed', 'Someone edited it at the same time. Check the new order.');
      }
      try {
        show(await request(fresh.version));
      } catch (retryError) {
        await load();
        alertError(retryError, 'Playlist changed');
      }
    }
  };

  const has = (p: PlaylistDetail, trackId: string | null) => trackId === null || p.tracks.some((t) => t.id === trackId);

  const moveAfter = (trackId: string, afterId: string | null) =>
    edit(
      (version) => post<PlaylistDetail>(`/playlists/${id}/tracks/${trackId}/move`, { after_track_id: afterId, version }),
      (p) => has(p, trackId) && has(p, afterId),
    );

  const move = (index: number, delta: -1 | 1) => {
    const tracks = latest.current!.tracks;
    const target = index + delta;
    if (target < 0 || target >= tracks.length) return;
    // "Up" = after the track two above (or first); "down" = after the next one.
    const afterId = delta === -1 ? (target === 0 ? null : tracks[target - 1].id) : tracks[target].id;
    moveAfter(tracks[index].id, afterId);
  };

  const remove = (trackId: string) =>
    edit(
      (version) => del<PlaylistDetail>(`/playlists/${id}/tracks/${trackId}?version=${version}`),
      (p) => has(p, trackId),
    );

  const add = (track: Track) =>
    edit(
      (version) =>
        post<PlaylistDetail>(`/playlists/${id}/tracks`, { provider: track.provider, external_id: track.external_id, version }),
      (p) => !p.tracks.some((t) => t.external_id === track.external_id),
    );

  if (!playlist) return error ? <ErrorText error={error} /> : <Loading />;

  return (
    <Screen onRefresh={load}>
      <Stack.Screen options={{ title: playlist.name }} />
      <Body muted>
        by {playlist.owner.display_name} · {playlist.visibility} · {playlist.can_edit ? 'you can edit' : 'read only'} · v
        {playlist.version}
      </Body>
      {playlist.description ? <Body>{playlist.description}</Body> : null}
      {deviceId && playlist.tracks.length ? (
        <Button
          title="Play on this phone"
          kind="secondary"
          onPress={() =>
            post(`/devices/${deviceId}/commands`, { command: 'play_playlist', playlist_id: playlist.id }).catch(alertError)
          }
        />
      ) : null}

      <Label>{playlist.tracks.length} tracks</Label>
      {playlist.tracks.map((t, index) => (
        <ListItem
          key={t.id}
          title={`${index + 1}. ${t.title}`}
          subtitle={`${t.artist} · ${formatDuration(t.duration)}`}
          right={
            playlist.can_edit ? (
              <Row gap={4}>
                <Button title="↑" small kind="secondary" disabled={index === 0} onPress={() => move(index, -1)} />
                <Button title="↓" small kind="secondary" disabled={index === playlist.tracks.length - 1} onPress={() => move(index, 1)} />
                <Button title="✕" small kind="danger" onPress={() => remove(t.id)} />
              </Row>
            ) : undefined
          }
        />
      ))}

      {playlist.can_edit ? (
        <Card>
          <Label>Add a track</Label>
          <TrackSearch actionLabel="Add" onPick={add} />
        </Card>
      ) : null}

      {playlist.is_owner ? <Members playlistId={playlist.id} /> : null}
    </Screen>
  );
}

function Members({ playlistId }: { playlistId: string }) {
  const [members, setMembers] = useState<UserSummary[]>([]);
  const [friends, setFriends] = useState<FriendOut[]>([]);

  const load = useCallback(async () => {
    const [m, f] = await Promise.all([
      get<UserSummary[]>(`/playlists/${playlistId}/members`),
      get<FriendOut[]>('/friends'),
    ]);
    setMembers(m);
    setFriends(f);
  }, [playlistId]);

  useFocusEffect(
    useCallback(() => {
      load().catch(alertError);
    }, [load]),
  );

  const memberIds = new Set(members.map((u) => u.id));
  return (
    <Card>
      <Label>Invited editors</Label>
      {friends.length === 0 ? <Body muted>Add friends to invite them.</Body> : null}
      {friends.map(({ user }) => (
        <Row key={user.id}>
          <Body>{user.display_name}</Body>
          {memberIds.has(user.id) ? (
            <Button
              title="Remove"
              small
              kind="danger"
              onPress={() => del(`/playlists/${playlistId}/members/${user.id}`).then(load).catch(alertError)}
            />
          ) : (
            <Button
              title="Invite"
              small
              kind="secondary"
              onPress={() => post(`/playlists/${playlistId}/members`, { user_id: user.id }).then(load).catch(alertError)}
            />
          )}
        </Row>
      ))}
    </Card>
  );
}
