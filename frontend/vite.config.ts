import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  resolve: { alias: { "@locales": path.resolve(__dirname, "../locales") } },
  server: {
    fs: { allow: [".."] },
    proxy: { "/api": { target: process.env.API_URL || "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  build: { rollupOptions: {output: {manualChunks: {leaflet: ["leaflet"]}}}, target: "es2019", chunkSizeWarningLimit: 250 },
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "دیہاڑی Dihari",
        short_name: "دیہاڑی",
        description: "Voice-first daily-wage work",
        lang: "ur",
        dir: "rtl",
        start_url: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#14532d",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
      workbox: {
        importScripts: ["/push-events.js"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api/, /^\/admin/],
        runtimeCaching: [
          { urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/, handler: "CacheFirst",
            options: { cacheName: "fonts", expiration: { maxEntries: 8, maxAgeSeconds: 31536000 } } },
          { urlPattern: /\/api\/(meta|ai\/capabilities)\b.*/, handler: "StaleWhileRevalidate", options: { cacheName: "meta" } },
        ],
      },
    }),
  ],
});
