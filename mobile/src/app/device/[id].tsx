// Remote control: send commands to a device (mine, or a friend's that delegated
// control to me). Every command is checked by the server against the license.
import { router, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert } from 'react-native';

import { get, post } from '@/api/client';
import type { Command, DeviceState, Playlist, Track } from '@/api/types';
import { TrackSearch } from '@/features/TrackSearch';
import { alertError } from '@/lib/errors';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, Label, ListItem, Row, Screen } from '@/ui/kit';

export default function RemoteControl() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [state, setState] = useState<DeviceState | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);

  const load = useCallback(async () => {
    try {
      setState(await get<DeviceState | null>(`/devices/${id}/state`));
    } catch (e) {
      alertError(e);
      router.back();
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
      get<Playlist[]>('/playlists?mine=true').then(setPlaylists).catch(() => {});
    }, [load]),
  );

  useRoom(`device:${id}`, (msg) => {
    if (msg.type === 'device.state') setState(msg.payload as DeviceState);
    else if (msg.type === 'access_revoked' || msg.type === 'device.deleted') {
      Alert.alert('Control removed', 'You can no longer control this device.');
      router.back();
    } else if (msg.type === 'resync') load();
  });

  const send = (command: Command) => post(`/devices/${id}/commands`, command).catch(alertError);
  const volume = state?.volume ?? 80;

  return (
    <Screen onRefresh={load}>
      <Card>
        <Label>Now</Label>
        <Body>{state?.track ? `${state.is_playing ? '▶' : '❚❚'} ${state.track.title} · ${state.track.artist}` : 'Nothing playing (or device offline)'}</Body>
        <Body muted>Volume {volume} %</Body>
        <Row>
          <Button title="⏮" kind="secondary" onPress={() => send({ command: 'previous' })} />
          <Button title={state?.is_playing ? 'Pause' : 'Play'} onPress={() => send({ command: state?.is_playing ? 'pause' : 'play' })} />
          <Button title="⏭" kind="secondary" onPress={() => send({ command: 'next' })} />
        </Row>
        <Row>
          <Button title="Vol −" small kind="secondary" onPress={() => send({ command: 'set_volume', volume: Math.max(0, volume - 10) })} />
          <Button title="Vol +" small kind="secondary" onPress={() => send({ command: 'set_volume', volume: Math.min(100, volume + 10) })} />
        </Row>
      </Card>

      <Card>
        <Label>Play a track</Label>
        <TrackSearch
          actionLabel="Play"
          onPick={async (track: Track) => {
            await send({ command: 'play_track', track: { provider: track.provider, external_id: track.external_id } });
          }}
        />
      </Card>

      {playlists.length ? <Label>Play one of my playlists</Label> : null}
      {playlists.map((p) => (
        <ListItem key={p.id} title={p.name} onPress={() => send({ command: 'play_playlist', playlist_id: p.id })} />
      ))}
    </Screen>
  );
}
