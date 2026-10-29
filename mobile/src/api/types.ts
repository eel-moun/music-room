// Readable names for the types generated from the backend's OpenAPI (src/api/schema.d.ts).
// Regenerate after a backend change: make mobile-api
import type { components } from './schema';

type S = components['schemas'];

export type Me = S['MeOut'];
export type Profile = S['ProfileOut'];
export type ProfileUpdate = S['ProfileUpdate'];
export type UserSummary = S['UserSummary'];
export type FriendOut = S['FriendOut'];
export type FriendRequest = S['FriendRequestOut'];
export type TokenPair = S['TokenPair'];
export type Track = S['TrackInfo'];
export type EventOut = S['EventOut'];
export type EventSettings = S['EventSettings'];
export type Queue = S['QueueOut'];
export type QueueTrack = S['QueueTrackOut'];
export type Playlist = S['PlaylistOut'];
export type PlaylistDetail = S['PlaylistDetail'];
export type PlaylistTrack = S['PlaylistTrackOut'];
export type Device = S['DeviceOut'];
export type ControllableDevice = S['ControllableDeviceOut'];
export type Delegation = S['DelegationOut'];
export type DeviceState = S['DeviceState'];
export type Command = S['CommandIn'];
