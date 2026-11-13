import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

// 管理台构建配置
// - 开发时把 /api 反代到本地后端（默认 http://127.0.0.1:8000）
// - 生产构建成纯静态资源，由 nginx 托管并反代 /api（见 admin/nginx.conf）
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());

  return {
    base: env.VITE_PUBLIC_PATH || "/",
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url))
      }
    },
    plugins: [vue()],
    server: {
      host: "0.0.0.0",
      port: Number(env.VITE_PORT) || 8848,
      proxy: {
        "/api": {
          target: env.VITE_PROXY_TARGET || "http://127.0.0.1:8000",
          changeOrigin: true
        }
      }
    },
    build: {
      target: "es2019",
      sourcemap: false,
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          chunkFileNames: "static/js/[name]-[hash].js",
          entryFileNames: "static/js/[name]-[hash].js",
          assetFileNames: "static/[ext]/[name]-[hash].[ext]",
          manualChunks: {
            "element-plus": ["element-plus"],
            vendor: ["vue", "vue-router", "pinia", "axios", "dayjs"]
          }
        }
      }
    }
  };
});
