import { router } from 'expo-router';
import { useState } from 'react';

import { post } from '@/api/client';
import type { EventOut, EventSettings } from '@/api/types';
import { message } from '@/lib/errors';
import { currentPosition, DEFAULT_POSITION } from '@/lib/location';
import { Body, Button, Card, Choice, ErrorText, Input, Row, Screen } from '@/ui/kit';

type Visibility = EventSettings['visibility'];
type License = EventSettings['license'];

export default function NewEvent() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('public');
  const [license, setLicense] = useState<License>('everyone');
  const [lat, setLat] = useState(DEFAULT_POSITION.latitude.toString());
  const [lng, setLng] = useState(DEFAULT_POSITION.longitude.toString());
  const [locStatus, setLocStatus] = useState<string | null>(null);
  const [radius, setRadius] = useState('200');
  const [hours, setHours] = useState('3');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const detectLocation = async () => {
    setLocStatus('Detecting GPS...');
    const pos = await currentPosition();
    if (pos) {
      setLat(pos.latitude.toFixed(5));
      setLng(pos.longitude.toFixed(5));
      setLocStatus('GPS location acquired ✓');
    } else {
      setLocStatus('GPS unavailable on HTTP (using preset coordinates)');
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      if (!name.trim()) throw new Error('Event name is required');
      const body: Partial<EventSettings> = { name: name.trim(), description, visibility, license };
      if (license === 'location_time') {
        const latitude = parseFloat(lat);
        const longitude = parseFloat(lng);
        if (isNaN(latitude) || latitude < -90 || latitude > 90) {
          throw new Error('Latitude must be a valid number between -90 and 90');
        }
        if (isNaN(longitude) || longitude < -180 || longitude > 180) {
          throw new Error('Longitude must be a valid number between -180 and 180');
        }
        const radiusNum = parseInt(radius, 10);
        if (isNaN(radiusNum) || radiusNum < 10 || radiusNum > 50000) {
          throw new Error('Radius must be between 10 and 50,000 meters');
        }
        const hoursNum = parseFloat(hours);
        if (isNaN(hoursNum) || hoursNum <= 0 || hoursNum > 168) {
          throw new Error('Voting window must be between 0.01 and 168 hours');
        }
        const now = new Date();
        Object.assign(body, {
          latitude,
          longitude,
          radius_m: radiusNum,
          starts_at: now.toISOString(),
          ends_at: new Date(now.getTime() + hoursNum * 3600_000).toISOString(),
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
            title="Use my current GPS"
            kind="secondary"
            onPress={detectLocation}
          />
          <Row>
            <Button
              title="42 Paris"
              small
              kind="secondary"
              onPress={() => {
                setLat('48.89668');
                setLng('2.31837');
                setLocStatus('Preset: 42 Paris');
              }}
            />
            <Button
              title="42 Silicon Valley"
              small
              kind="secondary"
              onPress={() => {
                setLat('37.5539');
                setLng('-121.9822');
                setLocStatus('Preset: 42 Silicon Valley');
              }}
            />
          </Row>
          {locStatus ? <Body muted>{locStatus}</Body> : null}
          <Input
            label="Latitude (-90 to 90)"
            keyboardType="numeric"
            value={lat}
            onChangeText={(t) => setLat(t.replace(/[^0-9.-]/g, ''))}
          />
          <Input
            label="Longitude (-180 to 180)"
            keyboardType="numeric"
            value={lng}
            onChangeText={(t) => setLng(t.replace(/[^0-9.-]/g, ''))}
          />
          <Input
            label="Radius in meters (10 to 50000)"
            keyboardType="number-pad"
            value={radius}
            onChangeText={(t) => setRadius(t.replace(/[^0-9]/g, '').slice(0, 5))}
          />
          <Input
            label="Voting window in hours (e.g. 0.05 for ~3 mins, or 3 for 3h)"
            keyboardType="decimal-pad"
            value={hours}
            onChangeText={(t) => setHours(t.replace(/[^0-9.]/g, '').slice(0, 6))}
          />
        </Card>
      ) : null}
      <ErrorText error={error} />
      <Button title="Create event" busy={busy} onPress={create} />
    </Screen>
  );
}
