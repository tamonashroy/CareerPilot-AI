import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "@/app/app";
import { applyTheme, resolveInitialTheme } from "@/components/theme/theme";
import "@/index.css";

// Set before the first render so the page doesn't flash the wrong theme.
applyTheme(resolveInitialTheme());

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
