// Shared helpers for the k6 scenarios. Runs inside the compose network (API=http://api:8000).
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';

export const API = __ENV.API || 'http://localhost:8000';
// Issued by `make loadtest-tokens` (open() only works in the init stage).
export const USERS = JSON.parse(open('./tokens.json'));

// A 409 on a playlist is the optimistic lock doing its job, not a server failure.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 409));
export const conflicts = new Counter('playlist_conflicts');

const DEVICE = { 'X-Platform': 'k6', 'X-Device': 'loadtest', 'X-App-Version': '1.0.0' };

export function headers(user) {
  return {
    headers: { ...DEVICE, Authorization: `Bearer ${user.token}`, 'Content-Type': 'application/json' },
  };
}

export function userFor(vu) {
  // VU 0 isn't used: user 0 is the host/owner created in setup.
  return USERS[1 + ((vu - 1) % (USERS.length - 1))];
}

export function call(method, path, user, body, name) {
  const params = { ...headers(user), tags: { name: name || path } };
  const payload = body === undefined ? null : JSON.stringify(body);
  return http.request(method, `${API}${path}`, payload, params);
}

export function ok(response, label) {
  return check(response, { [label]: (r) => r.status >= 200 && r.status < 300 });
}

// Real Audius ids, resolved once in setup (the provider is only called there).
export const TRACKS = ['YmJWK','mvG3AvQ','X9mJ01O','LW9rk','JbKjZ','pz9ym','2Vdld','2PZrK'];

export function setupWorld() {
  const host = USERS[0];
  const event = call('POST', '/events', host, { name: 'k6 party' }).json();
  for (const id of TRACKS) call('POST', `/events/${event.id}/tracks`, host, { external_id: id });
  const queue = call('GET', `/events/${event.id}/queue`, host).json();

  let playlist = call('POST', '/playlists', host, { name: 'k6 playlist' }).json();
  for (const id of TRACKS) {
    const r = call('POST', `/playlists/${playlist.id}/tracks`, host, { external_id: id, version: playlist.version });
    if (r.status === 201) playlist = r.json();
  }

  // Delegation needs friendship: befriend every load user, then grant control.
  const device = call('POST', '/devices', host, { name: 'k6 speaker', platform: 'k6' }).json();
  for (const user of USERS.slice(1)) {
    const req = call('POST', '/friends/requests', host, { user_id: user.id });
    if (req.status === 201) call('POST', `/friends/requests/${req.json().id}/accept`, user);
    call('POST', `/devices/${device.id}/delegations`, host, {
      grantee_id: user.id,
      permissions: ['playback', 'volume'],
    });
  }
  return {
    eventId: event.id,
    trackIds: queue.queue.map((t) => t.id),
    playlistId: playlist.id,
    deviceId: device.id,
  };
}
