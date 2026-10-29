import { Redirect } from 'expo-router';

import { useAuth } from '@/auth/AuthContext';
import { Loading } from '@/ui/kit';

export default function Index() {
  const { me, ready } = useAuth();
  if (!ready) return <Loading />;
  return <Redirect href={me ? '/events' : '/login'} />;
}
