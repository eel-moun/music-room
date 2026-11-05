import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Platform } from 'react-native';

import { ApiError, del, get, post } from '@/api/client';
import type { FriendOut, PlaylistDetail, Track, UserSummary } from '@/api/types';
import { formatDuration, TrackSearch } from '@/features/TrackSearch';
import { alertError, message } from '@/lib/errors';
import { useDeviceAgent } from '@/player/DeviceAgent';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, ErrorText, Input, Label, ListItem, Loading, Row, Screen } from '@/ui/kit';

export default function PlaylistScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { deviceId, state } = useDeviceAgent();
  const [playlist, setPlaylist] = useState<PlaylistDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const latest = useRef<PlaylistDetail | null>(null);

  const sendCommand = (cmd: string, extra: Record<string, unknown> = {}) => {
    if (!deviceId) return;
    post(`/devices/${deviceId}/commands`, { command: cmd, ...extra }).catch(alertError);
  };

  const isCurrentPlaylist = state.playlist_id === playlist?.id;

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

  const goBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace('/(tabs)/playlists');
    }
  };

  useRoom(`playlist:${id}`, (msg) => {
    if (msg.type === 'playlist.updated') {
      // Someone (maybe us) changed it: adopt the server's state and version.
      const current = latest.current;
      if (current) show({ ...current, ...msg.payload, can_edit: current.can_edit });
    } else if (msg.type === 'playlist.deleted' || msg.type === 'access_revoked') {
      Alert.alert('This playlist is no longer available');
      goBack();
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

  if (!playlist) {
    return (
      <Screen onRefresh={load}>
        <Stack.Screen
          options={{
            title: 'Playlist',
            headerLeft: Platform.OS === 'web' ? () => <Button title="← Back" small kind="secondary" onPress={goBack} /> : undefined,
          }}
        />
        {error ? (
          <Card>
            <ErrorText error={error} />
            <Button title="← Back to playlists" kind="secondary" onPress={goBack} />
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
          title: playlist.name,
          headerLeft: Platform.OS === 'web' ? () => <Button title="← Back" small kind="secondary" onPress={goBack} /> : undefined,
        }}
      />
      <Body muted>
        by {playlist.owner.display_name} · {playlist.visibility} · {playlist.can_edit ? 'you can edit' : 'read only'} · v
        {playlist.version}
      </Body>
      {playlist.description ? <Body>{playlist.description}</Body> : null}
      {deviceId && playlist.tracks.length ? (
        isCurrentPlaylist && state.track ? (
          <Card>
            <Label>Now Playing</Label>
            <Body>{state.is_playing ? '▶' : '❚❚'} {state.track.title} · {state.track.artist}</Body>
            <Row>
              <Button title="⏮ Prev" small kind="secondary" onPress={() => sendCommand('previous')} />
              <Button
                title={state.is_playing ? '❚❚ Pause' : '▶ Play'}
                small
                kind={state.is_playing ? 'secondary' : 'primary'}
                onPress={() => sendCommand(state.is_playing ? 'pause' : 'play')}
              />
              <Button title="⏭ Next" small kind="secondary" onPress={() => sendCommand('next')} />
            </Row>
          </Card>
        ) : (
          <Button
            title="▶ Play playlist"
            kind="primary"
            onPress={() => sendCommand('play_playlist', { playlist_id: playlist.id })}
          />
        )
      ) : null}

      <Label>{playlist.tracks.length} tracks</Label>
      {playlist.tracks.map((t, index) => {
        const isTrackPlaying = state.track?.external_id === t.external_id && state.is_playing;
        return (
          <ListItem
            key={t.id}
            title={`${index + 1}. ${t.title}`}
            subtitle={`${t.artist} · ${formatDuration(t.duration)}`}
            left={
              deviceId ? (
                <Button
                  title={isTrackPlaying ? '❚❚' : '▶'}
                  small
                  kind={isTrackPlaying ? 'primary' : 'secondary'}
                  onPress={() => {
                    if (isTrackPlaying) {
                      sendCommand('pause');
                    } else {
                      sendCommand('play_track', {
                        track: { provider: t.provider, external_id: t.external_id },
                        playlist_id: playlist.id,
                      });
                    }
                  }}
                />
              ) : undefined
            }
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
        );
      })}

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
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSummary[]>([]);
  const [searching, setSearching] = useState(false);

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
      await post(`/playlists/${playlistId}/members`, { user_id: userId });
      await load();
    } catch (e) {
      alertError(e);
    }
  };

  const removeUser = async (userId: string) => {
    try {
      await del(`/playlists/${playlistId}/members/${userId}`);
      await load();
    } catch (e) {
      alertError(e);
    }
  };

  const memberIds = new Set(members.map((u) => u.id));

  return (
    <Card>
      <Label>Invited editors ({members.length})</Label>
      {members.length === 0 ? <Body muted>No one invited yet.</Body> : null}
      {members.map((u) => (
        <Row key={u.id}>
          <Body>{u.display_name}</Body>
          <Button
            title="Remove"
            small
            kind="danger"
            onPress={() => removeUser(u.id)}
          />
        </Row>
      ))}

      <Label>Invite editor by display name</Label>
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
              {memberIds.has(u.id) ? (
                <Button title="Remove" small kind="danger" onPress={() => removeUser(u.id)} />
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
              {memberIds.has(user.id) ? (
                <Button
                  title="Remove"
                  small
                  kind="danger"
                  onPress={() => removeUser(user.id)}
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
