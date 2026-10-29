// This phone as a "device" (Control Delegation): registered once per install,
// it listens to its room and obeys commands sent by the owner or delegated friends,
// then reports its state so the controllers' screens update.
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus, type AudioPlayer } from 'expo-audio';
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Platform } from 'react-native';

import { get, post, put } from '@/api/client';
import type { Device, DeviceState, PlaylistDetail, Track } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { deviceName } from '@/lib/device';
import { load, save } from '@/lib/storage';
import { useRoom } from '@/realtime/useRoom';

type Agent = { deviceId: string | null; state: DeviceState };
type Queue = { tracks: Track[]; index: number; playlistId: string | null };

const IDLE: DeviceState = { is_playing: false, volume: 80, position_s: 0, track: null, playlist_id: null };
const AgentContext = createContext<Agent>({ deviceId: null, state: IDLE });

async function ensureDevice(): Promise<string> {
  const known = await load('deviceId');
  const mine = await get<Device[]>('/devices');
  if (known && mine.some((d) => d.id === known)) return known;
  const device = await post<Device>('/devices', { name: deviceName, platform: Platform.OS });
  await save('deviceId', device.id);
  return device.id;
}

/** Applies commands to the audio player. Plain class: no React state, so the
 *  command handler never sees a stale copy of the device state. */
class Controller {
  state: DeviceState = IDLE;
  queue: Queue = { tracks: [], index: 0, playlistId: null };

  constructor(
    private player: () => AudioPlayer,
    private onChange: (state: DeviceState) => void,
  ) {}

  private update(patch: Partial<DeviceState>) {
    this.state = { ...this.state, ...patch };
    this.onChange(this.state);
  }

  private async playTrack(track: Track) {
    // Signed, short-lived URL: fetched right before playing.
    const { url } = await get<{ url: string }>(`/music/tracks/${track.external_id}/stream`);
    this.player().replace(url);
    this.player().play();
    this.update({ is_playing: true, track, playlist_id: this.queue.playlistId, position_s: 0 });
  }

  async step(delta: number) {
    const index = this.queue.index + delta;
    if (index < 0 || index >= this.queue.tracks.length) return this.update({ is_playing: false });
    this.queue.index = index;
    await this.playTrack(this.queue.tracks[index]);
  }

  async apply(command: { command: string; [arg: string]: any }, currentTime: number) {
    switch (command.command) {
      case 'play':
        this.player().play();
        return this.update({ is_playing: true });
      case 'pause':
        this.player().pause();
        return this.update({ is_playing: false, position_s: Math.round(currentTime) });
      case 'set_volume':
        this.player().volume = command.volume / 100;
        return this.update({ volume: command.volume });
      case 'play_track':
        this.queue = { tracks: [command.track], index: 0, playlistId: null };
        return this.playTrack(command.track);
      case 'play_playlist': {
        const playlist = await get<PlaylistDetail>(`/playlists/${command.playlist_id}`);
        this.queue = { tracks: playlist.tracks, index: -1, playlistId: playlist.id };
        return this.step(1);
      }
      case 'next':
        return this.step(1);
      case 'previous':
        return this.step(-1);
    }
  }
}

export function DeviceAgent({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const [registered, setRegistered] = useState<string | null>(null);
  const [state, setState] = useState<DeviceState>(IDLE);
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const playerRef = useRef(player);
  const deviceIdRef = useRef<string | null>(null);
  const controller = useRef<Controller | null>(null);

  useEffect(() => {
    playerRef.current = player;
  }, [player]);

  useEffect(() => {
    controller.current = new Controller(
      () => playerRef.current,
      (next) => {
        setState(next);
        const id = deviceIdRef.current;
        if (id) put(`/devices/${id}/state`, next).catch(() => {});
      },
    );
    setAudioModeAsync({ playsInSilentMode: true, shouldPlayInBackground: true, interruptionMode: 'doNotMix' });
  }, []);

  useEffect(() => {
    if (!me) return;
    ensureDevice()
      .then((id) => {
        deviceIdRef.current = id;
        setRegistered(id);
      })
      .catch(() => {});
  }, [me]);

  const deviceId = me ? registered : null;

  // Next track of a playlist when the current one ends.
  useEffect(() => {
    if (status.didJustFinish && controller.current?.queue.tracks.length) {
      controller.current.step(1).catch(() => {});
    }
  }, [status.didJustFinish]);

  useRoom(deviceId ? `device:${deviceId}` : null, (event) => {
    if (event.type !== 'device.command') return;
    // A failed command (e.g. Audius unreachable) leaves the state unchanged: the
    // controller sees no update and can retry.
    controller.current?.apply(event.payload, status.currentTime).catch(() => {});
  });

  return <AgentContext.Provider value={{ deviceId, state }}>{children}</AgentContext.Provider>;
}

export function useDeviceAgent(): Agent {
  return useContext(AgentContext);
}
