import { useColorScheme } from 'react-native';

const light = {
  bg: '#F7F7FA',
  card: '#FFFFFF',
  text: '#15151A',
  muted: '#6B6B76',
  border: '#E3E3EA',
  primary: '#5B4BDB',
  primaryText: '#FFFFFF',
  danger: '#C62828',
  success: '#2E7D32',
};

const dark: typeof light = {
  bg: '#0F0F13',
  card: '#1A1A21',
  text: '#F1F1F5',
  muted: '#9A9AA6',
  border: '#2C2C36',
  primary: '#8B7DFF',
  primaryText: '#0F0F13',
  danger: '#EF6B6B',
  success: '#66BB6A',
};

export type Colors = typeof light;

export function useColors(): Colors {
  return useColorScheme() === 'dark' ? dark : light;
}
