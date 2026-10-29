import { useState } from 'react';
import { View } from 'react-native';

import { get } from '@/api/client';
import type { Track } from '@/api/types';
import { message } from '@/lib/errors';
import { Button, ErrorText, Input, ListItem, Row } from '@/ui/kit';

export function formatDuration(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** Search Audius through our API and act on a result ("Suggest", "Add", "Play"). */
export function TrackSearch({ actionLabel, onPick }: { actionLabel: string; onPick: (t: Track) => Promise<void> }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Track[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResults(await get<Track[]>(`/music/search?q=${encodeURIComponent(query.trim())}&limit=15`));
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: 8 }}>
      <Row>
        <View style={{ flex: 1 }}>
          <Input placeholder="Search a track or artist" value={query} onChangeText={setQuery} onSubmitEditing={search} returnKeyType="search" />
        </View>
        <Button title="Search" onPress={search} busy={busy} small />
      </Row>
      <ErrorText error={error} />
      {results.map((track) => (
        <ListItem
          key={track.external_id}
          title={track.title}
          subtitle={`${track.artist} · ${formatDuration(track.duration)}`}
          right={
            <Button
              title={actionLabel}
              small
              kind="secondary"
              onPress={() => onPick(track).catch((e) => setError(message(e)))}
            />
          }
        />
      ))}
    </View>
  );
}
