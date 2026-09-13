import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["recharts"],
          react: [
            "react",
            "react-dom",
            "react-router-dom",
            "@tanstack/react-query",
          ],
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.BACKEND_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: process.env.BACKEND_TARGET || "http://127.0.0.1:8000",
      },
      "/ws": {
        target: process.env.BACKEND_TARGET || "http://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
