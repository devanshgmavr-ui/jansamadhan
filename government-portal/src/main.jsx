import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { GovAuthProvider } from "./context/GovAuthContext.jsx";
import "./index.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <GovAuthProvider>
        <App />
      </GovAuthProvider>
    </BrowserRouter>
  </StrictMode>
);
