import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { post } from '@/api/client';
import { message } from '@/lib/errors';
import { Button, Card, ErrorText, Input, Screen } from '@/ui/kit';

export default function Register() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await post('/auth/register', { display_name: name.trim(), email: email.trim(), password });
      Alert.alert('Check your inbox', 'Open the verification link we sent you, then log in.');
      router.back();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Card>
        <Input label="Display name" autoCapitalize="words" value={name} onChangeText={setName} />
        <Input label="Email" keyboardType="email-address" value={email} onChangeText={setEmail} />
        <Input label="Password (8+ characters)" secureTextEntry value={password} onChangeText={setPassword} />
        <ErrorText error={error} />
        <Button title="Create account" busy={busy} onPress={submit} />
      </Card>
    </Screen>
  );
}
