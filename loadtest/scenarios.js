// What one virtual user does in each service. Think times model a real person;
// `fast` drops them (stress test: each iteration is pure load).
import { sleep } from 'k6';
import { WebSocket } from 'k6/websockets';
import { API, call, conflicts, ok, userFor } from './lib.js';

export function voter(world, fast = false) {
  const user = userFor(__VU);
  const queue = call('GET', `/events/${world.eventId}/queue`, user, undefined, 'GET /events/{id}/queue');
  ok(queue, 'queue read');
  const track = world.trackIds[Math.floor(Math.random() * world.trackIds.length)];
  const path = `/events/${world.eventId}/tracks/${track}/vote`;
  const name = 'vote /events/{id}/tracks/{id}/vote';
  // Vote or withdraw (409 = the track was picked as now-playing meanwhile: fine).
  const method = Math.random() < 0.7 ? 'POST' : 'DELETE';
  ok(call(method, path, user, method === 'POST' ? {} : undefined, `${method} ${name}`), 'vote');
  if (!fast) sleep(1 + Math.random() * 2);
}

export function editor(world, fast = false) {
  const user = userFor(__VU);
  const res = call('GET', `/playlists/${world.playlistId}`, user, undefined, 'GET /playlists/{id}');
  if (!ok(res, 'playlist read')) return;
  const playlist = res.json();
  const tracks = playlist.tracks;
  const moving = tracks[Math.floor(Math.random() * tracks.length)];
  const after = Math.random() < 0.2 ? null : tracks[Math.floor(Math.random() * tracks.length)].id;
  if (after === moving.id) return;
  const move = call(
    'POST',
    `/playlists/${world.playlistId}/tracks/${moving.id}/move`,
    user,
    { after_track_id: after, version: playlist.version },
    'POST /playlists/{id}/tracks/{id}/move',
  );
  if (move.status === 409) conflicts.add(1);
  if (!fast) sleep(2 + Math.random() * 3);
}

export function controller(world, fast = false) {
  const user = userFor(__VU);
  const commands = [{ command: 'play' }, { command: 'pause' }, { command: 'set_volume', volume: 50 }];
  const body = commands[Math.floor(Math.random() * commands.length)];
  ok(call('POST', `/devices/${world.deviceId}/commands`, user, body, 'POST /devices/{id}/commands'), 'command');
  if (!fast) sleep(2 + Math.random() * 3);
}

// A phone sitting on the event screen: one socket, receiving every queue update.
export function listener(world) {
  const user = userFor(__VU);
  const ws = new WebSocket(`${API.replace('http', 'ws')}/ws`);
  ws.onopen = () => {
    ws.send(JSON.stringify({ type: 'auth', token: user.token }));
    ws.send(JSON.stringify({ type: 'subscribe', room: `event:${world.eventId}` }));
  };
  ws.onerror = (e) => console.error(`ws error: ${e.error}`);
  setTimeout(() => ws.close(), 30000); // stay 30 s, then reconnect (next iteration)
}
