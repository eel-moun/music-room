import { useEffect, useEffectEvent } from 'react';

import { realtime, type RoomEvent } from './socket';

/** Subscribe to a room while the component is mounted. */
export function useRoom(room: string | null, onEvent: (event: RoomEvent) => void) {
  // Always calls the latest onEvent without resubscribing when it changes.
  const handle = useEffectEvent(onEvent);

  useEffect(() => {
    if (!room) return;
    return realtime.subscribe(room, (event) => handle(event));
  }, [room]);
}
