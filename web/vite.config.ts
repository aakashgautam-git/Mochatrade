import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const api = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    // The Django dev server. Keeps the client on one origin so the demo never
    // trips over CORS on a conference network.
    proxy: api,
  },
  // `npm run preview` serves the production build against the same backend.
  preview: { port: 4173, strictPort: true, proxy: api },
  build: {
    rollupOptions: {
      output: {
        // Vendor code in its own long-lived chunks: the app changes far more
        // often than React or the chart library, and no chunk tops 500 kB.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return "react";
          if (/[\\/](recharts|d3-[^\\/]+|victory-vendor|internmap|decimal\.js-light|lodash|react-smooth|recharts-scale|eventemitter3|tiny-invariant|fast-equals|clsx|react-is|prop-types)[\\/]/.test(id)) return "charts";
          if (/[\\/](@tanstack|zustand|use-sync-external-store)[\\/]/.test(id)) return "state";
          if (/[\\/]lucide-react[\\/]/.test(id)) return "icons";
          return undefined;
        },
      },
    },
  },
});
