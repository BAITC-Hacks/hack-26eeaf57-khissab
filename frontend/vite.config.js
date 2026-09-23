import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const explicitProxyTarget = process.env.VITE_API_PROXY_TARGET;
const publicApiUrl = process.env.VITE_API_URL;
const proxyTarget =
  explicitProxyTarget || (/^https?:\/\//.test(publicApiUrl || "") ? publicApiUrl : "http://127.0.0.1:8000");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
