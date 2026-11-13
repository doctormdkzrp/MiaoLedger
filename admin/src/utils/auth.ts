/** 登录态存储：token 与用户信息都放 localStorage，刷新页面后仍在。 */

export type Role = "admin" | "user";

export interface UserInfo {
  username: string;
  display_name: string;
  role: Role;
}

const TOKEN_KEY = "miao-token";
const USER_KEY = "miao-user";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as UserInfo;
    if (!data || !data.username) return null;
    return data;
  } catch {
    return null;
  }
}

export function setUser(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLogged(): boolean {
  return Boolean(getToken());
}

export function isAdmin(): boolean {
  return getUser()?.role === "admin";
}
