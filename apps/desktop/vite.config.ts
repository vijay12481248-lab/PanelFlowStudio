import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

const rootDir = path.resolve(__dirname, "../..");
const localAppData = process.env.LOCALAPPDATA || "";
const appDataTokenFile = path.resolve(localAppData, "PanelFlow Studio", "engine.token");
const rootTokenFile = path.resolve(rootDir, ".engine_token");

const getEngineToken = () => {
  if (process.env.PANELFLOW_ENGINE_TOKEN) return process.env.PANELFLOW_ENGINE_TOKEN.trim();
  if (localAppData && fs.existsSync(appDataTokenFile)) {
    try {
      return fs.readFileSync(appDataTokenFile, "utf-8").trim();
    } catch {}
  }
  if (fs.existsSync(rootTokenFile)) {
    try {
      return fs.readFileSync(rootTokenFile, "utf-8").trim();
    } catch {}
  }
  return "";
};

export default defineConfig({
  plugins: [
    react(),
    {
      name: "panelflow-engine-token",
      configureServer(server) {
        server.middlewares.use("/__engine_token", (_req, res) => {
          res.setHeader("Content-Type", "text/plain");
          res.end(getEngineToken());
        });
      },
    },
  ],
  clearScreen: false,
  define: {
    "import.meta.env.VITE_PANELFLOW_ENGINE_TOKEN": JSON.stringify(getEngineToken()),
  },
  optimizeDeps: {
    entries: ['index.html'],
  },
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
  resolve: {
    alias: {
      "@panelflow/history": path.resolve(__dirname, "../../packages/history/src/index.ts"),
      "@panelflow/shared-types": path.resolve(__dirname, "../../packages/shared-types/src/index.ts"),
      "@panelflow/api-client": path.resolve(__dirname, "../../packages/api-client/src/index.ts"),
      "@panelflow/ui-v2": path.resolve(__dirname, "../../packages/ui/src/v2/index.ts"),
      "@panelflow/ui": path.resolve(__dirname, "../../packages/ui/src/index.tsx"),
    },
  },
});
