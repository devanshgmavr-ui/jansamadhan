import { useCallback, useEffect, useState } from "react";
import { authApi, clearTokens, getTokens, saveTokens } from "../services/api";
import { AuthContext } from "./useAuth";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getTokens()?.access_token) await fetchMe();
      setInitializing(false);
    })();
  }, [fetchMe]);

  const login = async (identifier, password) => {
    const tokens = await authApi.login({ identifier, password });
    saveTokens(tokens);
    return fetchMe();
  };

  const logout = async () => {
    const tokens = getTokens();
    try {
      if (tokens) await authApi.logout(tokens.refresh_token, tokens.access_token);
    } catch {
      /* session already invalid — clear locally regardless */
    }
    clearTokens();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, initializing, login, logout, fetchMe, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}
