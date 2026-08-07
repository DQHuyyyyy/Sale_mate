import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import * as api from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // 'loading' cho tới khi biết chắc còn phiên hay không — tránh nháy về /login.
  const [loading, setLoading] = useState(true);

  const signOut = useCallback(() => {
    api.logout();
    setUser(null);
  }, []);

  useEffect(() => {
    api.setUnauthorizedHandler(() => setUser(null));

    if (!api.getToken()) {
      setLoading(false);
      return;
    }
    api
      .getMe()
      .then(setUser)
      .catch(() => api.logout())
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (username, password) => {
    await api.login(username, password);
    // Lấy lại từ /api/auth/me để nguồn sự thật luôn là backend.
    const me = await api.getMe();
    setUser(me);
    return me;
  }, []);

  const value = useMemo(
    () => ({
      user,
      role: user?.role ?? null,
      isAdmin: user?.role === 'admin',
      isSale: user?.role === 'sale',
      loading,
      signIn,
      signOut,
    }),
    [user, loading, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth phải nằm trong <AuthProvider>');
  return context;
}
