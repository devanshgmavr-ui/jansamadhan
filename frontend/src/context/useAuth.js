import { createContext, useContext } from "react";

// Authentication context object and hook live together in this
// components-free module so AuthContext.jsx exports only the provider
// (react-refresh/only-export-components).
export const AuthContext = createContext(null);

export function useAuth() {
  return useContext(AuthContext);
}
