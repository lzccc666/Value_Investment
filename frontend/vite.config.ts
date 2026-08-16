import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backendPort = process.env.VITE_BACKEND_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": `http://127.0.0.1:${backendPort}`
    }
  },
  preview: {
    host: "127.0.0.1",
    port: 4173
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/tests/setup.ts"
  }
});
