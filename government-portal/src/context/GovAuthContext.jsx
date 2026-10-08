import { useCallback, useEffect, useState } from "react";
import { GovAuthContext } from "./useGovAuth";
import {
  clearSession,
  getToken,
  govAuthApi,
  saveSession,
} from "../services/govApi";

export function GovAuthProvider({ children }) {
  const [official, setOfficial] = useState(null);
  const [initializing, setInitializing] = useState(true);

  const fetchMe = useCallback(async () => {
    try {
      const me = await govAuthApi.me();
      setOfficial(me);
      return me;
    } catch {
      setOfficial(null);
      return null;
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getToken()) await fetchMe();
      setInitializing(false);
    })();
  }, [fetchMe]);

  const login = async (employeeId, password) => {
    const session = await govAuthApi.login({
      employee_id: employeeId,
      password,
    });
    saveSession(session);
    return fetchMe();
  };

  const logout = async () => {
    try {
      await govAuthApi.logout();
    } catch {
      // Session already invalid — clear locally regardless.
    }
    clearSession();
    setOfficial(null);
  };

  return (
    <GovAuthContext.Provider
      value={{
        official,
        initializing,
        isAuthenticated: Boolean(official),
        login,
        logout,
        refresh: fetchMe,
      }}
    >
      {children}
    </GovAuthContext.Provider>
  );
}
