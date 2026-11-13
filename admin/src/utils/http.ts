import axios from "axios";
import type {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig
} from "axios";
import { ElMessage } from "element-plus";
import { clearAuth, getToken } from "./auth";

/** 额外请求选项：silent 时不弹错误提示，由调用方自己处理。 */
export interface RequestOptions extends AxiosRequestConfig {
  silent?: boolean;
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 20000,
  headers: { "Content-Type": "application/json" }
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

/** 把后端返回的 detail 转成人话：可能是字符串，也可能是 pydantic 的数组。 */
function detailToMessage(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map(item => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean);
    return parts.join("；");
  }
  if (typeof detail === "object" && "msg" in (detail as Record<string, unknown>)) {
    return String((detail as { msg: unknown }).msg);
  }
  return "";
}

function goLogin(): void {
  clearAuth();
  const { hash } = window.location;
  if (!hash.startsWith("#/login")) {
    window.location.hash = "#/login";
  }
}

/**
 * 有些接口用 401 表示「凭据不对」而不是「登录失效」——改密码时旧密码输错就是这种情况。
 * 只有 detail 明确是 token 问题（或用户不存在）时才算登录失效，其它 401 只提示、不踢人。
 */
const SESSION_EXPIRED_HINTS = ["缺少 token", "token 无效", "用户不存在"];

function isSessionExpired(status: number, msg: string, url: string): boolean {
  if (status !== 401) return false;
  // 登录接口本身的 401 是账号密码不对，不该当成会话失效
  if (url.includes("/auth/login") || url.includes("/auth/change-pin")) return false;
  if (!msg) return true;
  return SESSION_EXPIRED_HINTS.some(hint => msg.includes(hint));
}

http.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const options = (error.config || {}) as RequestOptions;
    const status = error.response?.status ?? 0;
    const data = error.response?.data as unknown;
    const url = String((error.config as AxiosRequestConfig | undefined)?.url || "");

    let msg = "";
    if (data instanceof Blob) {
      msg = "下载失败了，稍后再试";
    } else if (data && typeof data === "object") {
      msg = detailToMessage((data as { detail?: unknown }).detail);
    }

    if (isSessionExpired(status, msg, url)) {
      const expiredMsg = msg || "登录状态失效了，请重新登录";
      if (!options.silent) ElMessage.error(expiredMsg);
      goLogin();
      return Promise.reject(new Error(expiredMsg));
    }

    if (!msg) {
      if (status === 0) msg = "连不上服务器，检查网络后重试";
      else if (status === 403) msg = "没有权限干这件事";
      else if (status === 404) msg = "要找的东西不存在了";
      else if (status >= 500) msg = "服务器出了点问题，稍后再试";
      else if (status === 401) msg = "账号或密码不对";
      else msg = `请求失败了（${status}）`;
    }

    if (!options.silent) ElMessage.error(msg);
    return Promise.reject(new Error(msg));
  }
);

/** 统一解包：后端直接返回 JSON body。 */
export async function request<T = unknown>(options: RequestOptions): Promise<T> {
  const response = await http.request<T>(options);
  return response.data;
}

export function get<T = unknown>(
  url: string,
  params?: Record<string, unknown>,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>({ ...options, url, method: "get", params });
}

export function post<T = unknown>(
  url: string,
  data?: unknown,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>({ ...options, url, method: "post", data });
}

export function put<T = unknown>(
  url: string,
  data?: unknown,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>({ ...options, url, method: "put", data });
}

export function patch<T = unknown>(
  url: string,
  data?: unknown,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>({ ...options, url, method: "patch", data });
}

export function del<T = unknown>(
  url: string,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>({ ...options, url, method: "delete" });
}

/**
 * 下载文件（CSV 导出）：必须走 axios 带上 Authorization，
 * 用浏览器直接打开链接不会带 token，所以拿 blob 再触发保存。
 */
export async function download(
  url: string,
  params: Record<string, unknown>,
  filename: string,
  options: RequestOptions = {}
): Promise<void> {
  const response = await http.request<Blob>({
    ...options,
    url,
    method: "get",
    params,
    responseType: "blob"
  });

  const blob = response.data;
  const contentType = response.headers["content-type"] || "text/csv;charset=utf-8";
  const typed = blob.type ? blob : new Blob([blob], { type: String(contentType) });
  const href = URL.createObjectURL(typed);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(href);
}

/** 上传文件（CSV 导入）。 */
export async function upload<T = unknown>(
  url: string,
  file: File,
  field = "file",
  options: RequestOptions = {}
): Promise<T> {
  const form = new FormData();
  form.append(field, file);
  return request<T>({
    ...options,
    url,
    method: "post",
    data: form,
    headers: { "Content-Type": "multipart/form-data" }
  });
}

export default http;
