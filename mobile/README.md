# Music Room: mobile app

Expo (SDK 58) + expo-router. The app is a "remote control" for the backend: it sends commands over REST and receives state over one WebSocket.

## Run

```bash
cp .env.example .env     # EXPO_PUBLIC_API_URL=http://<PC LAN IP>:8000
npm install
npx expo start           # Expo Go (iPhone): everything except Google sign-in
npx expo run:android     # development build on a USB-connected Android phone (Google sign-in included)
```

The backend URL can also be changed in the app: login screen → **Server settings**.

## Structure

```
src/app/          screens (expo-router: one file per route)
  (tabs)/         Track Vote, Playlists, Devices, Friends, Profile
  event/ playlist/ device/ user/   detail screens
src/api/          REST client (token refresh), types generated from the backend's OpenAPI
src/auth/         session context, Google Sign-In (development build only)
src/realtime/     WebSocket client: rooms, reconnect with backoff, resync on gaps
src/player/       DeviceAgent: this phone as a controllable device
src/features/     track search, host player
src/lib/          secure storage, backend URL, device headers, location
src/ui/           shared components and theme
```

## Notes

- Tokens and the device id live in the OS keystore (expo-secure-store).
- Every request sends `X-Platform`, `X-Device` and `X-App-Version`: the backend logs each action with them.
- Refreshes are serialized: the server treats a replayed refresh token as theft.
- Playlist edits carry the version the app last saw. On a 409 the app refetches and re-applies the user's change once if it still makes sense.
- `npx tsc --noEmit` and `npx expo lint` must pass (CI runs both). Regenerate the API types after a backend change: `make mobile-api` from the repo root.
