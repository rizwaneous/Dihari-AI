import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { registerSW } from "virtual:pwa-register";
import App from "./App";
import { I18nProvider } from "./i18n";
import { SessionProvider } from "./session";
import "./index.css";
import "./market.css";

registerSW({ immediate: true });
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <I18nProvider>
        <SessionProvider>
          <App />
        </SessionProvider>
      </I18nProvider>
    </BrowserRouter>
  </StrictMode>,
);
