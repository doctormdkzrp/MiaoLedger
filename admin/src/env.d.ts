/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}

interface ImportMetaEnv {
  /** 接口基地址，默认 /api（同源反代）。 */
  readonly VITE_API_BASE_URL?: string;
  /** 本地开发时 vite 代理的后端地址。 */
  readonly VITE_PROXY_TARGET?: string;
  readonly VITE_PUBLIC_PATH?: string;
  readonly VITE_PORT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
