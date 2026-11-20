import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => {
  // 같은 Wi-Fi의 휴대폰 테스트는 인증서를 지정한 경우에만 연다.
  const key = process.env.FITIF_LAN_TLS_KEY;
  const cert = process.env.FITIF_LAN_TLS_CERT;
  if (command === "serve" && Boolean(key) !== Boolean(cert)) {
    throw new Error("FITIF_LAN_TLS_KEY와 FITIF_LAN_TLS_CERT를 함께 설정해 주세요.");
  }
  const https = command === "serve" && key && cert
    ? { key: readFileSync(key), cert: readFileSync(cert) }
    : undefined;

  return {
    plugins: [react()],
    server: {
      allowedHosts: ["pastel-grove-shed.ngrok-free.dev"],
      host: https ? "0.0.0.0" : undefined,
      https,
      // 기존 Windows SSH 터널을 사용한다.
      proxy: {
        "/api": { target: "http://127.0.0.1:18002", changeOrigin: true },
      },
    },
  };
});
