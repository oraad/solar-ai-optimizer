import { constants as zlibConstants } from "node:zlib";
import { defineConfig } from "vite";
import { compression, defineAlgorithm } from "vite-plugin-compression2";

// During `vite dev`, proxy API + WebSocket to the backend so the dashboard can
// run on :5173 while the backend runs on :8000. In production the dashboard is
// served by the FastAPI backend itself (single container).
//
// `base: "./"` makes built asset URLs relative so the app works when served at
// "/" (standalone) or under a Home Assistant ingress path prefix.
export default defineConfig({
  plugins: [
    compression({
      threshold: 1024,
      exclude: [/\.(br|gz)$/],
      algorithms: [
        defineAlgorithm("gzip", { level: 9 }),
        defineAlgorithm("brotliCompress", {
          params: { [zlibConstants.BROTLI_PARAM_QUALITY]: 11 },
        }),
      ],
    }),
  ],
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
