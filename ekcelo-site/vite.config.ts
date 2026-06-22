import { defineConfig } from "vite";
import { fileURLToPath, URL } from "node:url";

// Proxy /api → бэкенд (uvicorn на localhost:8000). cookies passthrough — для
// session-cookie ekcelo_token из cycle 14 M2.
const BACKEND_URL = process.env.EKCELO_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  resolve: {
    alias: {
      "@core": fileURLToPath(new URL("./src/core", import.meta.url)),
      "@adapters": fileURLToPath(new URL("./src/adapters", import.meta.url)),
      "@ui": fileURLToPath(new URL("./src/ui", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Все REST-эндпоинты бэкенда пробрасываются через /api/* без префикса.
      "/api": {
        target: BACKEND_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // OAuth browser flow напрямую (без префикса) — чтобы redirect_uri совпал.
      "/auth": {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    include: ["tests/**/*.test.ts", "src/**/*.test.ts"],
  },
});
