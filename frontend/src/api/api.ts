import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import { ElLoading, ElMessage, type LoadingInstance } from "element-plus";

import type { ResponseModel } from "@/api/auth";

declare module "axios" {
  export interface AxiosRequestConfig {
    showLoading?: boolean;
  }

  export interface InternalAxiosRequestConfig {
    loadingStarted?: boolean;
  }
}

type UnauthorizedHandler = () => void | Promise<void>;

let activeLoadingRequests = 0;
let loadingInstance: LoadingInstance | undefined;
let unauthorizedHandler: UnauthorizedHandler = defaultUnauthorizedHandler;

const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000",
  timeout: 10_000,
  withCredentials: true,
});

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    if (config.showLoading !== false) {
      config.loadingStarted = true;
      startLoading();
    }
    return config;
  },
  (error: unknown): Promise<never> => Promise.reject(error),
);

api.interceptors.response.use(
  (response) => {
    finishLoading(response.config);
    return response;
  },
  (error: AxiosError<ResponseModel<unknown>>): Promise<never> => {
    finishLoading(error.config);
    const status = error.response?.status;
    if (status === 401) {
      void unauthorizedHandler();
    } else if (status !== undefined && status >= 500) {
      ElMessage.error("服务器内部错误，请稍后重试");
    } else if (!error.response) {
      ElMessage.error("网络连接失败，请检查网络后重试");
    }
    return Promise.reject(error);
  },
);

/** Configure application navigation after an unauthorized response. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

/** Restore the browser-based unauthorized handler. */
export function resetUnauthorizedHandler(): void {
  unauthorizedHandler = defaultUnauthorizedHandler;
}

/** Start or retain the shared full-screen request loading mask. */
function startLoading(): void {
  activeLoadingRequests += 1;
  if (activeLoadingRequests === 1) {
    loadingInstance = ElLoading.service({
      lock: true,
      text: "加载中…",
      background: "rgb(15 23 42 / 18%)",
    });
  }
}

/** Close the shared loading mask after every tracked request completes. */
function finishLoading(config?: InternalAxiosRequestConfig): void {
  if (!config?.loadingStarted) {
    return;
  }
  config.loadingStarted = false;
  activeLoadingRequests = Math.max(0, activeLoadingRequests - 1);
  if (activeLoadingRequests === 0) {
    loadingInstance?.close();
    loadingInstance = undefined;
  }
}

/** Navigate directly to Login when no router integration is configured. */
function defaultUnauthorizedHandler(): void {
  if (typeof window === "undefined" || window.location.pathname === "/login") {
    return;
  }
  const redirect = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/login?redirect=${encodeURIComponent(redirect)}`);
}

export default api;
