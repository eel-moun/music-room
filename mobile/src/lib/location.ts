import * as Location from 'expo-location';

export type Position = { latitude: number; longitude: number };

export const DEFAULT_POSITION: Position = { latitude: 48.89668, longitude: 2.31837 }; // 42 Paris

/** The phone's position, or null if the user refuses or if blocked by browser HTTP. */
export async function currentPosition(): Promise<Position | null> {
  try {
    const { granted } = await Location.requestForegroundPermissionsAsync();
    if (!granted) return null;
    const { coords } = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    return { latitude: coords.latitude, longitude: coords.longitude };
  } catch {
    // Browsers on HTTP (non-secure context) reject geolocation permissions
    return null;
  }
}
