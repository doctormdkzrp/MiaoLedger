import { get, post } from "@/utils/http";
import type { ChangePinIn, ChangePinOut, LoginIn, TokenOut } from "./types";

/** 登录：用户名 + 6 位数字密码。 */
export function login(data: LoginIn): Promise<TokenOut> {
  return post<TokenOut>("/v1/auth/login", { ...data, device_name: data.device_name || "web-admin" }, {
    silent: true
  });
}

/** 退出登录：吊销当前 token。 */
export function logout(): Promise<{ ok: boolean; revoked: boolean }> {
  return post("/v1/auth/logout", undefined, { silent: true });
}

/** 修改自己的 6 位数字密码（其它设备会被踢下线）。 */
export function changePin(data: ChangePinIn): Promise<ChangePinOut> {
  return post<ChangePinOut>("/v1/auth/change-pin", data, { silent: true });
}

export interface CheckUsernameOut {
  available: boolean;
  reason: string;
}

/** 注册前查账号名是否可用（管理台建号时也用得上）。 */
export function checkUsername(username: string): Promise<CheckUsernameOut> {
  return get<CheckUsernameOut>("/v1/auth/check-username", { username }, { silent: true });
}
