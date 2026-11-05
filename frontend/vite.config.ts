
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  // React에서 /api로 시작하는 요청을
  // Windows SSH 터널을 통해 3060 서버로 전달
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18002",
        changeOrigin: true,
      },
    },
  },
});
