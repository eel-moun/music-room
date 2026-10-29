import { router } from 'expo-router';
import { useState } from 'react';

import { post } from '@/api/client';
import type { EventOut, EventSettings } from '@/api/types';
import { message } from '@/lib/errors';
import { currentPosition, type Position } from '@/lib/location';
import { Body, Button, Card, Choice, ErrorText, Input, Screen } from '@/ui/kit';

type Visibility = EventSettings['visibility'];
type License = EventSettings['license'];

export default function NewEvent() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('public');
  const [license, setLicense] = useState<License>('everyone');
  const [position, setPosition] = useState<Position | null>(null);
  const [radius, setRadius] = useState('200');
  const [hours, setHours] = useState('3');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const body: Partial<EventSettings> = { name: name.trim(), description, visibility, license };
      if (license === 'location_time') {
        if (!position) throw new Error('Set the event location first');
        const now = new Date();
        Object.assign(body, {
          ...position,
          radius_m: Number(radius),
          starts_at: now.toISOString(),
          ends_at: new Date(now.getTime() + Number(hours) * 3600_000).toISOString(),
        });
      }
      const event = await post<EventOut>('/events', body);
      router.replace({ pathname: '/event/[id]', params: { id: event.id } });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Card>
        <Input label="Name" value={name} onChangeText={setName} autoCapitalize="sentences" />
        <Input label="Description" value={description} onChangeText={setDescription} multiline />
        <Choice
          label="Who can find it"
          value={visibility}
          onChange={setVisibility}
          options={[
            { value: 'public', label: 'Everyone' },
            { value: 'private', label: 'Invited only' },
          ]}
        />
        <Choice
          label="Who can vote"
          value={license}
          onChange={setLicense}
          options={[
            { value: 'everyone', label: 'Everyone' },
            { value: 'invited', label: 'Invited only' },
            { value: 'location_time', label: 'People here, now' },
          ]}
        />
      </Card>
      {license === 'location_time' ? (
        <Card>
          <Button
            title={position ? 'Location set ✓ (tap to update)' : 'Use my current location'}
            kind="secondary"
            onPress={async () => setPosition(await currentPosition())}
          />
          {position ? (
            <Body muted>
              {position.latitude.toFixed(5)}, {position.longitude.toFixed(5)}
            </Body>
          ) : null}
          <Input label="Radius (meters)" keyboardType="number-pad" value={radius} onChangeText={setRadius} />
          <Input label="Voting open for (hours, from now)" keyboardType="decimal-pad" value={hours} onChangeText={setHours} />
        </Card>
      ) : null}
      <ErrorText error={error} />
      <Button title="Create event" busy={busy} onPress={create} />
    </Screen>
  );
}
