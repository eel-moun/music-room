import * as Location from 'expo-location';

export type Position = { latitude: number; longitude: number };

/** The phone's position, or null if the user refuses. Sent to the server for
 *  location-licensed events (the server decides; GPS can be faked: ADR-006). */
export async function currentPosition(): Promise<Position | null> {
  const { granted } = await Location.requestForegroundPermissionsAsync();
  if (!granted) return null;
  const { coords } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { latitude: coords.latitude, longitude: coords.longitude };
}
