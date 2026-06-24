import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (/node_modules\/(recharts|d3-|decimal\.js|react-smooth|victory-vendor)/.test(id)) {
            return "charts";
          }
          if (/node_modules\/(react|react-dom|react-router|scheduler)/.test(id)) {
            return "react-vendor";
          }
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/chat": "http://127.0.0.1:8000",
    },
  },
});
