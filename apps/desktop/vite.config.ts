import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
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
      "@panelflow/ui": path.resolve(__dirname, "../../packages/ui/src/index.tsx"),
    },
  },
});
