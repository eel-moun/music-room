import { Alert } from 'react-native';

import { ApiError } from '@/api/client';

export function message(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : 'Something went wrong';
}

export function alertError(error: unknown, title = 'Error') {
  Alert.alert(title, message(error));
}
