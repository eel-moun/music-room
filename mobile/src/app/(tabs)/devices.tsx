import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';

import { del, get, post } from '@/api/client';
import type { ControllableDevice, Delegation, Device, FriendOut } from '@/api/types';
import { useAuth } from '@/auth/AuthContext';
import { alertError, message } from '@/lib/errors';
import { useDeviceAgent } from '@/player/DeviceAgent';
import { useRoom } from '@/realtime/useRoom';
import { Body, Button, Card, Choice, ErrorText, Label, ListItem, Row, Screen } from '@/ui/kit';

type Permissions = 'playback' | 'volume' | 'both';
type Expiry = 'never' | '1' | '24';

const PERMISSIONS: Record<Permissions, string[]> = {
  playback: ['playback'],
  volume: ['volume'],
  both: ['playback', 'volume'],
};

function DeviceDelegations({ device, friends }: { device: Device; friends: FriendOut[] }) {
  const [delegations, setDelegations] = useState<Delegation[]>([]);
  const [open, setOpen] = useState(false);
  const [friendId, setFriendId] = useState<string>('');
  const [permissions, setPermissions] = useState<Permissions>('both');
  const [expiry, setExpiry] = useState<Expiry>('never');

  const load = useCallback(async () => {
    setDelegations(await get<Delegation[]>(`/devices/${device.id}/delegations`));
  }, [device.id]);

  const grant = async () => {
    try {
      const expires_at =
        expiry === 'never' ? null : new Date(Date.now() + Number(expiry) * 3600_000).toISOString();
      await post(`/devices/${device.id}/delegations`, {
        grantee_id: friendId,
        permissions: PERMISSIONS[permissions],
        expires_at,
      });
      await load();
    } catch (e) {
      alertError(e);
    }
  };

  return (
    <Card>
      <Row>
        <Body>{device.name}</Body>
        <Body muted>({device.platform})</Body>
      </Row>
      <Button
        title={open ? 'Hide control licenses' : 'Who can control it?'}
        small
        kind="secondary"
        onPress={() => {
          setOpen(!open);
          if (!open) load().catch(alertError);
        }}
      />
      {open ? (
        <>
          {delegations.map((d) => (
            <ListItem
              key={d.id}
              title={d.grantee.display_name}
              subtitle={`${d.permissions.join(' + ')} · ${d.expires_at ? `until ${new Date(d.expires_at).toLocaleString()}` : 'no expiry'}`}
              right={
                <Button
                  title="Revoke"
                  small
                  kind="danger"
                  onPress={() => del(`/devices/${device.id}/delegations/${d.id}`).then(load).catch(alertError)}
                />
              }
            />
          ))}
          {friends.length === 0 ? (
            <Body muted>Add friends first: control can only be given to friends.</Body>
          ) : (
            <>
              <Choice
                label="Give control to"
                value={friendId}
                onChange={setFriendId}
                options={friends.map((f) => ({ value: f.user.id, label: f.user.display_name }))}
              />
              <Choice
                label="Allowed"
                value={permissions}
                onChange={setPermissions}
                options={[
                  { value: 'both', label: 'Playback + volume' },
                  { value: 'playback', label: 'Playback' },
                  { value: 'volume', label: 'Volume' },
                ]}
              />
              <Choice
                label="For"
                value={expiry}
                onChange={setExpiry}
                options={[
                  { value: 'never', label: 'Until revoked' },
                  { value: '1', label: '1 hour' },
                  { value: '24', label: '24 hours' },
                ]}
              />
              <Button title="Grant" disabled={!friendId} onPress={grant} />
            </>
          )}
        </>
      ) : null}
    </Card>
  );
}

export default function Devices() {
  const { me } = useAuth();
  const { deviceId, state } = useDeviceAgent();
  const [mine, setMine] = useState<Device[]>([]);
  const [controllable, setControllable] = useState<ControllableDevice[]>([]);
  const [friends, setFriends] = useState<FriendOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, c, f] = await Promise.all([
        get<Device[]>('/devices'),
        get<ControllableDevice[]>('/devices/controllable'),
        get<FriendOut[]>('/friends'),
      ]);
      setMine(m);
      setControllable(c);
      setFriends(f);
      setError(null);
    } catch (e) {
      setError(message(e));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );
  useRoom(me ? `user:${me.id}` : null, (event) => {
    if (event.type.startsWith('delegation.') || event.type === 'resync') load();
  });

  return (
    <Screen onRefresh={load}>
      <Card>
        <Label>This phone</Label>
        <Body>{state.track ? `${state.is_playing ? '▶' : '❚❚'} ${state.track.title}` : 'Nothing playing'}</Body>
        <Body muted>Volume {state.volume} %. Friends you allow can control what plays here.</Body>
        {deviceId ? (
          <Button
            title="Control this phone"
            small
            kind="secondary"
            onPress={() => router.push({ pathname: '/device/[id]', params: { id: deviceId } })}
          />
        ) : null}
      </Card>
      <ErrorText error={error} />

      <Label>My devices</Label>
      {mine.map((d) => (
        <DeviceDelegations key={d.id} device={d} friends={friends} />
      ))}

      <Label>{"Friends' devices I can control"}</Label>
      {controllable.length === 0 ? <Body muted>None yet. A friend has to give you control.</Body> : null}
      {controllable.map((d) => (
        <ListItem
          key={d.id}
          title={`${d.name} (${d.owner.display_name})`}
          subtitle={`${d.permissions.join(' + ')}${d.expires_at ? ` · until ${new Date(d.expires_at).toLocaleTimeString()}` : ''}`}
          onPress={() => router.push({ pathname: '/device/[id]', params: { id: d.id } })}
        />
      ))}
    </Screen>
  );
}
