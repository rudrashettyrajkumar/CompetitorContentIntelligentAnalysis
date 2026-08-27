import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// Dev: Vite serves the SPA on :5173 and proxies /api to the FastAPI dev server.
// Build: emits to ../frontend/dist which FastAPI serves at / via StaticFiles.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            "/api": "http://localhost:8000",
        },
    },
    build: {
        outDir: "dist",
        emptyOutDir: true,
    },
});
