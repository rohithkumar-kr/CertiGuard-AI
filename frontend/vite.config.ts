import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Dev-only: forward /api to the backend so the browser always talks to a
    // single origin (http://localhost:5173). The app prefers VITE_API_BASE_URL
    // when set; the proxy is the fallback and also removes any CORS dependency.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
