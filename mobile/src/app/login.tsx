import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { ApiError, post } from '@/api/client';
import { useAuth } from '@/auth/AuthContext';
import { googleAvailable } from '@/auth/google';
import { getApiUrl } from '@/lib/config';
import { message } from '@/lib/errors';
import { Body, Button, Card, ErrorText, Input, Screen } from '@/ui/kit';

export default function Login() {
  const { login, loginWithGoogle } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unverified, setUnverified] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.replace('/events');
    } catch (e) {
      setUnverified(e instanceof ApiError && e.code === 'email_not_verified');
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    await post('/auth/resend-verification', { email: email.trim() }).catch(() => {});
    Alert.alert('Email sent', 'Open the link in the email, then log in.');
  };

  return (
    <Screen>
      <Card>
        <Input label="Email" keyboardType="email-address" autoComplete="email" value={email} onChangeText={setEmail} />
        <Input label="Password" secureTextEntry autoComplete="password" value={password} onChangeText={setPassword} />
        <ErrorText error={error} />
        {unverified ? <Button title="Resend verification email" kind="secondary" onPress={resend} /> : null}
        <Button title="Log in" busy={busy} onPress={() => run(() => login(email.trim(), password))} />
        {googleAvailable ? (
          <Button title="Continue with Google" kind="secondary" onPress={() => run(loginWithGoogle)} />
        ) : null}
      </Card>
      <Button title="Create an account" kind="secondary" onPress={() => router.push('/register')} />
      <Button title="Forgot password?" kind="secondary" onPress={() => router.push('/forgot')} />
      <Button title={`Server: ${getApiUrl()}`} kind="secondary" small onPress={() => router.push('/settings')} />
      {!googleAvailable ? (
        <Body muted>{"Google sign-in needs the development build (it isn't available in Expo Go)."}</Body>
      ) : null}
    </Screen>
  );
}
