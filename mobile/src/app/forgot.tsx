import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { post } from '@/api/client';
import { message } from '@/lib/errors';
import { Body, Button, Card, ErrorText, Input, Screen } from '@/ui/kit';

export default function Forgot() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = async () => {
    setError(null);
    try {
      await post('/auth/forgot-password', { email: email.trim() });
      setSent(true);
    } catch (e) {
      setError(message(e));
    }
  };

  const reset = async () => {
    setError(null);
    try {
      await post('/auth/reset-password', { token: code.trim(), new_password: password });
      Alert.alert('Password changed', 'You can log in with your new password.');
      router.back();
    } catch (e) {
      setError(message(e));
    }
  };

  return (
    <Screen>
      <Card>
        <Input label="Email" keyboardType="email-address" value={email} onChangeText={setEmail} />
        <Button
          title={sent ? 'Send again' : 'Send me a reset code'}
          onPress={request}
          kind={sent ? 'secondary' : 'primary'}
        />
      </Card>
      {sent ? (
        <Card>
          <Body muted>Paste the code from the email and choose a new password.</Body>
          <Input label="Code" value={code} onChangeText={setCode} />
          <Input label="New password" secureTextEntry value={password} onChangeText={setPassword} />
          <Button title="Change password" onPress={reset} />
        </Card>
      ) : null}
      <ErrorText error={error} />
    </Screen>
  );
}
