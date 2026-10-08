import { createContext, useContext } from "react";

// Government session context object + hook. Kept in this component-free
// module so the provider file exports only the provider
// (react-refresh/only-export-components). Never shared with the public app.
export const GovAuthContext = createContext(null);

export function useGovAuth() {
  return useContext(GovAuthContext);
}
