import React from "react";
import ReactDOM from "react-dom/client";
import { NarrationStudioPreview } from "./components/narration-studio/NarrationStudioPreview";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <NarrationStudioPreview />
  </React.StrictMode>
);
