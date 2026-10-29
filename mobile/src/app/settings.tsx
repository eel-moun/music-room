import { router } from 'expo-router';
import { useState } from 'react';

import { DEFAULT_API_URL, getApiUrl, setApiUrl } from '@/lib/config';
import { deviceHeaders } from '@/lib/device';
import { Body, Button, Card, ErrorText, Input, Screen } from '@/ui/kit';

export default function Settings() {
  const [url, setUrl] = useState(getApiUrl());
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const test = async () => {
    setStatus(null);
    setError(null);
    try {
      const response = await fetch(`${url.trim().replace(/\/+$/, '')}/health`);
      setStatus(JSON.stringify(await response.json()));
    } catch {
      setError(`Can't reach ${url}. Same Wi-Fi as the server? Right IP and port?`);
    }
  };

  return (
    <Screen>
      <Card>
        <Input label="Backend URL" keyboardType="url" value={url} onChangeText={setUrl} placeholder={DEFAULT_API_URL} />
        <Button title="Test connection" kind="secondary" onPress={test} />
        {status ? <Body>{status}</Body> : null}
        <ErrorText error={error} />
        <Button
          title="Save"
          onPress={async () => {
            await setApiUrl(url);
            router.back();
          }}
        />
      </Card>
      <Card>
        <Body muted>Sent with every request (backend logs):</Body>
        <Body>
          {deviceHeaders['X-Platform']} · {deviceHeaders['X-Device']} · v{deviceHeaders['X-App-Version']}
        </Body>
      </Card>
    </Screen>
  );
}
