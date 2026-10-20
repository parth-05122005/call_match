import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Send /api requests to Django, so the browser sees one origin (no CORS setup).
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});