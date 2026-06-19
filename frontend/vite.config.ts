import { defineConfig } from "vite";

// During `vite dev`, proxy API + WebSocket to the backend so the dashboard can
// run on :5173 while the backend runs on :8000. In production the dashboard is
// served by the FastAPI backend itself (single container).
//
// `base: "./"` makes built asset URLs relative so the app works when served at
// "/" (standalone) or under a Home Assistant ingress path prefix.
export default defineConfig({
  base: "./",
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    target: "es2021",
    outDir: "dist",
    sourcemap: true,
  },
});
