import { defineStore } from "pinia";
import { login as loginApi, logout as logoutApi } from "@/api/auth";
import type { LoginIn, TokenOut } from "@/api/types";
import { clearAuth, getToken, getUser, setToken, setUser, type UserInfo } from "@/utils/auth";

interface UserState {
  token: string;
  user: UserInfo | null;
}

export const useUserStore = defineStore("miao-user", {
  state: (): UserState => ({
    token: getToken(),
    user: getUser()
  }),

  getters: {
    isLogged: (state): boolean => Boolean(state.token),
    displayName: (state): string => state.user?.display_name || state.user?.username || "",
    /** 顶栏与菜单都用它判断要不要显示管理功能。 */
    isAdmin: (state): boolean => state.user?.role === "admin"
  },

  actions: {
    async login(payload: LoginIn): Promise<TokenOut> {
      const data = await loginApi(payload);
      this.token = data.token;
      this.user = {
        username: data.username,
        display_name: data.display_name,
        role: data.role
      };
      setToken(data.token);
      setUser(this.user);
      return data;
    },

    /** 退出：先通知后端吊销 token，失败也照常清本地。 */
    async logout(): Promise<void> {
      try {
        await logoutApi();
      } catch {
        // 网络异常或 token 已失效，本地照清
      }
      this.token = "";
      this.user = null;
      clearAuth();
    },

    /** 只清本地状态（401 时用，避免再发请求）。 */
    reset(): void {
      this.token = "";
      this.user = null;
      clearAuth();
    },

    /** 从 localStorage 重新读一次：多标签页或外部改动后保持同步。 */
    hydrate(): void {
      this.token = getToken();
      this.user = getUser();
    },

    patchUser(patch: Partial<UserInfo>): void {
      if (!this.user) return;
      this.user = { ...this.user, ...patch };
      setUser(this.user);
    }
  }
});
