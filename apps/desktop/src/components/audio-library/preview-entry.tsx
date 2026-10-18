import React from "react";
import ReactDOM from "react-dom/client";
import { AudioLibraryPreviewHarness } from "./AudioLibraryPreviewHarness.tsx";
import "../../index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AudioLibraryPreviewHarness />
  </React.StrictMode>
);
