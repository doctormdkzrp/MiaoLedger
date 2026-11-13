import { del, download, get, patch, post, put, upload } from "@/utils/http";
import type {
  AdminTxnIn,
  AdminTxnPage,
  AdminUser,
  AdminUserIn,
  AdminUserPatchIn,
  AdminUserPatchOut,
  AiProfile,
  ImportResult,
  MetaOut,
  Role,
  Txn
} from "./types";

/** ---------------- 用户 ---------------- */

export function fetchUsers(): Promise<AdminUser[]> {
  return get<AdminUser[]>("/v1/admin/users");
}

export function createUser(data: AdminUserIn): Promise<AdminUser> {
  return post<AdminUser>("/v1/admin/users", data, { silent: true });
}

export function updateUser(userId: number, data: AdminUserPatchIn): Promise<AdminUserPatchOut> {
  return patch<AdminUserPatchOut>(`/v1/admin/users/${userId}`, data, { silent: true });
}

/** ---------------- 某用户的账本 / 分类 / 账户 ---------------- */

export function fetchUserMeta(userId: number): Promise<MetaOut> {
  return get<MetaOut>(`/v1/admin/users/${userId}/meta`);
}

/** ---------------- 某用户的账单 ---------------- */

export interface AdminTxnQuery {
  from?: string;
  to?: string;
  book_id?: number | null;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
}

export function fetchUserTxns(userId: number, query: AdminTxnQuery = {}): Promise<AdminTxnPage> {
  return get<AdminTxnPage>(`/v1/admin/users/${userId}/txns`, {
    limit: query.limit ?? 200,
    offset: query.offset ?? 0,
    include_deleted: query.include_deleted ?? false,
    ...(query.from ? { from: query.from } : {}),
    ...(query.to ? { to: query.to } : {}),
    ...(query.book_id != null ? { book_id: query.book_id } : {})
  });
}

export function createUserTxn(userId: number, data: AdminTxnIn): Promise<Txn> {
  return post<Txn>(`/v1/admin/users/${userId}/txns`, data, { silent: true });
}

export function patchUserTxn(
  userId: number,
  clientUuid: string,
  data: Record<string, unknown>
): Promise<Txn> {
  return patch<Txn>(`/v1/admin/users/${userId}/txns/${encodeURIComponent(clientUuid)}`, data, {
    silent: true
  });
}

export function removeUserTxn(userId: number, clientUuid: string): Promise<{ ok: boolean }> {
  return del(`/v1/admin/users/${userId}/txns/${encodeURIComponent(clientUuid)}`, { silent: true });
}

/** ---------------- 某用户的 AI 提示词 ---------------- */

export function fetchUserProfile(userId: number): Promise<AiProfile> {
  return get<AiProfile>(`/v1/admin/users/${userId}/ai-profile`);
}

export function saveUserProfile(userId: number, hints: string): Promise<AiProfile> {
  return put<AiProfile>(`/v1/admin/users/${userId}/ai-profile`, { hints }, { silent: true });
}

/** ---------------- CSV 导入导出 ---------------- */

export function exportUserCsv(userId: number, from: string, to: string, bookId?: number | null) {
  return download(
    `/v1/admin/users/${userId}/export.csv`,
    { from, to, ...(bookId != null ? { book_id: bookId } : {}) },
    `用户${userId}-${from}_${to}.csv`
  );
}

export function importUserCsv(userId: number, file: File): Promise<ImportResult> {
  return upload<ImportResult>(`/v1/admin/users/${userId}/import/csv`, file);
}

export type { AdminUser, Role };
