// The event owner's phone plays the queue: the now-playing track streams here, and
// when it ends the server is asked for the next one (the top-voted track).
import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { useEffect, useRef } from 'react';

import { get, post } from '@/api/client';
import type { Queue } from '@/api/types';
import { alertError } from '@/lib/errors';
import { Body, Button, Card, Label, Row } from '@/ui/kit';

export function HostPlayer({ eventId, queue }: { eventId: string; queue: Queue }) {
  const player = useAudioPlayer(null);
  const status = useAudioPlayerStatus(player);
  const loadedId = useRef<string | null>(null);
  const advancing = useRef(false);
  const nowPlaying = queue.now_playing;

  const next = async () => {
    if (advancing.current) return;
    advancing.current = true;
    try {
      await post(`/events/${eventId}/next`); // the new queue arrives through the socket
    } catch (e) {
      alertError(e);
    } finally {
      advancing.current = false;
    }
  };

  // Load the stream when the server picks a new track. Stream URLs are signed and
  // short-lived, so they're fetched right before playing, never stored.
  useEffect(() => {
    if (!nowPlaying || nowPlaying.id === loadedId.current) return;
    loadedId.current = nowPlaying.id;
    get<{ url: string }>(`/music/tracks/${nowPlaying.external_id}/stream`)
      .then(({ url }) => {
        player.replace(url);
        player.play();
      })
      .catch(alertError);
  }, [nowPlaying, player]);

  useEffect(() => {
    if (status.didJustFinish) next();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.didJustFinish]);

  return (
    <Card>
      <Label>Host player (this phone plays the party)</Label>
      <Body>{nowPlaying ? `${nowPlaying.title} · ${nowPlaying.artist}` : 'Not started'}</Body>
      {nowPlaying ? (
        <Body muted>
          {Math.floor(status.currentTime)} / {Math.floor(status.duration || nowPlaying.duration)} s
        </Body>
      ) : null}
      <Row>
        {nowPlaying ? (
          <Button title={status.playing ? 'Pause' : 'Resume'} small kind="secondary" onPress={() => (status.playing ? player.pause() : player.play())} />
        ) : null}
        <Button title={nowPlaying ? 'Skip to next' : 'Start the party'} small onPress={next} disabled={!nowPlaying && queue.queue.length === 0} />
      </Row>
    </Card>
  );
}
