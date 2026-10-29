// Sent with every request: the backend logs each action with them (subject V.6).
import * as Application from 'expo-application';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { Platform } from 'react-native';

export const deviceHeaders = {
  'X-Platform': Platform.OS,
  'X-Device': Device.modelName ?? 'unknown',
  'X-App-Version': Application.nativeApplicationVersion ?? Constants.expoConfig?.version ?? '0.0.0',
};

export const deviceName = Device.deviceName ?? Device.modelName ?? `${Platform.OS} device`;
