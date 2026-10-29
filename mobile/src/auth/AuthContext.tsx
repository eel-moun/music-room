import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { get, post, setSessionExpiredHandler, storeTokens } from '@/api/client';
import type { Me, TokenPair } from '@/api/types';
import { loadApiUrl } from '@/lib/config';
import { load } from '@/lib/storage';
import { realtime } from '@/realtime/socket';

import { getGoogleIdToken, googleSignOut } from './google';

type Auth = {
  me: Me | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
  reloadMe: () => Promise<void>;
};

const AuthContext = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  const reloadMe = useCallback(async () => {
    setMe(await get<Me>('/users/me'));
  }, []);

  const startSession = useCallback(
    async (tokens: TokenPair) => {
      await storeTokens(tokens);
      await reloadMe();
      realtime.start();
    },
    [reloadMe],
  );

  const clearSession = useCallback(async () => {
    realtime.stop();
    await storeTokens(null);
    setMe(null);
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() => void clearSession());
    (async () => {
      await loadApiUrl();
      if (await load('refreshToken')) {
        try {
          await reloadMe(); // refreshes the access token if needed
          realtime.start();
        } catch {
          // Offline or session revoked: stay logged out.
        }
      }
      setReady(true);
    })();
  }, [clearSession, reloadMe]);

  const value = useMemo<Auth>(
    () => ({
      me,
      ready,
      reloadMe,
      login: async (email, password) => {
        await startSession(await post<TokenPair>('/auth/login', { email, password }));
      },
      loginWithGoogle: async () => {
        const idToken = await getGoogleIdToken();
        if (idToken) await startSession(await post<TokenPair>('/auth/google', { id_token: idToken }));
      },
      logout: async () => {
        const refreshToken = await load('refreshToken');
        if (refreshToken) await post('/auth/logout', { refresh_token: refreshToken }).catch(() => {});
        await googleSignOut();
        await clearSession();
      },
    }),
    [me, ready, reloadMe, startSession, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth outside AuthProvider');
  return auth;
}
