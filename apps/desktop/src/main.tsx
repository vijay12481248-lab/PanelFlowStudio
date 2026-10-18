import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { ErrorProvider } from "./context/ErrorContext";
import "./index.css";

document.getElementById("bootstrap-status")?.remove();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorProvider>
      <App />
    </ErrorProvider>
  </React.StrictMode>
);
