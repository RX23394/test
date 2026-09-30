import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

const elementMocks = vi.hoisted(() => ({
  close: vi.fn(),
  loading: vi.fn(),
  messageError: vi.fn(),
}));

vi.mock("element-plus", () => ({
  ElLoading: {
    service: elementMocks.loading.mockReturnValue({ close: elementMocks.close }),
  },
  ElMessage: { error: elementMocks.messageError },
}));

import api, {
  resetUnauthorizedHandler,
  setUnauthorizedHandler,
} from "@/api/api";

describe("unified Axios client", () => {
  afterEach(() => {
    vi.clearAllMocks();
    resetUnauthorizedHandler();
  });

  it("uses credentials and manages the shared loading mask", async () => {
    await api.get("/success", {
      adapter: async (config) => ({
        data: { status: "ok" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      }),
    });

    expect(api.defaults.withCredentials).toBe(true);
    expect(elementMocks.loading).toHaveBeenCalledOnce();
    expect(elementMocks.close).toHaveBeenCalledOnce();
  });

  it("allows individual requests to disable global loading", async () => {
    await api.get("/quiet", {
      showLoading: false,
      adapter: async (config) => ({
        data: { status: "ok" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      }),
    });

    expect(elementMocks.loading).not.toHaveBeenCalled();
  });

  it("invokes the configured login handler for a 401 response", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(
      api.get("/private", {
        adapter: async (config) => {
          throw new AxiosError(
            "Unauthorized",
            "ERR_BAD_REQUEST",
            config,
            undefined,
            {
              data: { status: "error", message: "Authentication required" },
              status: 401,
              statusText: "Unauthorized",
              headers: {},
              config,
            },
          );
        },
      }),
    ).rejects.toBeInstanceOf(AxiosError);

    expect(handler).toHaveBeenCalledOnce();
    expect(elementMocks.close).toHaveBeenCalledOnce();
  });

  it("shows unified messages for server and network failures", async () => {
    await expect(
      api.get("/server-error", {
        adapter: async (config) => {
          throw new AxiosError("Server error", "ERR_BAD_RESPONSE", config, undefined, {
            data: { status: "error" },
            status: 500,
            statusText: "Server Error",
            headers: {},
            config,
          });
        },
      }),
    ).rejects.toBeInstanceOf(AxiosError);
    await expect(
      api.get("/network-error", {
        adapter: async (config) => {
          throw new AxiosError("Network Error", "ERR_NETWORK", config);
        },
      }),
    ).rejects.toBeInstanceOf(AxiosError);

    expect(elementMocks.messageError).toHaveBeenNthCalledWith(
      1,
      "服务器内部错误，请稍后重试",
    );
    expect(elementMocks.messageError).toHaveBeenNthCalledWith(
      2,
      "网络连接失败，请检查网络后重试",
    );
  });
});
