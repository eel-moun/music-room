// One WebSocket for the whole app. Screens subscribe to rooms ("event:<id>", ...).
// The server is the source of truth: after a reconnect or a gap in `seq`, handlers
// get a { type: 'resync' } event and refetch over REST.
import { get } from '@/api/client';
import { getApiUrl } from '@/lib/config';
import { deviceHeaders } from '@/lib/device';
import { load } from '@/lib/storage';

export type RoomEvent = { type: string; room: string; seq?: number; payload: any };
type Handler = (event: RoomEvent) => void;

class Realtime {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private lastSeq = new Map<string, number>();
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = true;

  start() {
    this.stopped = false;
    if (!this.ws) this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }

  subscribe(room: string, handler: Handler): () => void {
    if (!this.handlers.has(room)) {
      this.handlers.set(room, new Set());
      this.send({ type: 'subscribe', room });
    }
    this.handlers.get(room)!.add(handler);
    return () => {
      const set = this.handlers.get(room);
      set?.delete(handler);
      if (set && set.size === 0) {
        this.handlers.delete(room);
        this.lastSeq.delete(room);
        this.send({ type: 'unsubscribe', room });
      }
    };
  }

  private send(message: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message));
  }

  private async connect() {
    const token = await load('accessToken');
    if (!token || this.stopped) return;
    const url = getApiUrl().replace(/^http/, 'ws') + '/ws';
    // React Native's WebSocket accepts headers (browsers don't): device info for the logs.
    const ws = new (WebSocket as any)(url, null, { headers: deviceHeaders }) as WebSocket;
    this.ws = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', token }));
    };
    ws.onmessage = (message) => this.onMessage(JSON.parse(message.data));
    ws.onclose = async (event) => {
      this.ws = null;
      if (this.stopped) return;
      // 4401: the access token expired. Any REST call refreshes it before we retry.
      if (event.code === 4401) await get('/users/me').catch(() => {});
      // Exponential backoff, capped at 30 s.
      const delay = Math.min(30_000, 1000 * 2 ** this.retry++);
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }

  private onMessage(message: RoomEvent) {
    if (message.type === 'ready') {
      this.retry = 0;
      // (Re)join every room, then let screens refetch what they may have missed.
      for (const room of this.handlers.keys()) {
        this.send({ type: 'subscribe', room });
        this.emit(room, { type: 'resync', room, payload: null });
      }
      return;
    }
    if (message.type === 'subscribed') {
      this.lastSeq.set(message.room, message.payload.seq);
      return;
    }
    if (message.type === 'unsubscribed') {
      this.emit(message.room, { ...message, type: 'access_revoked' });
      return;
    }
    if (message.seq === undefined) return;

    const last = this.lastSeq.get(message.room);
    this.lastSeq.set(message.room, message.seq);
    if (last !== undefined && message.seq > last + 1) {
      // Missed events (pub/sub keeps nothing): refetch instead of trusting partial state.
      this.emit(message.room, { type: 'resync', room: message.room, payload: null });
      return;
    }
    this.emit(message.room, message);
  }

  private emit(room: string, event: RoomEvent) {
    this.handlers.get(room)?.forEach((handler) => handler(event));
  }
}

export const realtime = new Realtime();
