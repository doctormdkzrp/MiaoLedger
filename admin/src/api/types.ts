/** 与后端 schemas.py 对齐的类型定义。 */

export type Role = "admin" | "user";
export type TxnKind = "out" | "in" | "transfer";

export interface TokenOut {
  token: string;
  username: string;
  display_name: string;
  role: Role;
}

export interface LoginIn {
  username: string;
  pin: string;
  device_name?: string;
}

export interface ChangePinIn {
  old_pin: string;
  new_pin: string;
}

export interface ChangePinOut {
  ok: boolean;
  revoked_devices: number;
}

export interface MeOut {
  username: string;
  display_name: string;
  role: Role;
  books: number;
  accounts: number;
  categories: number;
  txns: number;
}

export interface Book {
  id: number;
  name: string;
  icon: string;
  sort: number;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  kind: TxnKind;
  icon: string;
  sort: number;
}

export interface Account {
  id: number;
  name: string;
  kind: string;
  balance0_cents: number;
  sort: number;
}

export interface MetaOut {
  books: Book[];
  categories: Category[];
  accounts: Account[];
}

export interface Txn {
  id: number;
  client_uuid: string;
  book_id: number | null;
  cat_id: number | null;
  account_id: number | null;
  kind: TxnKind;
  amount_cents: number;
  occurred_at: string;
  note: string;
  source: string;
  deleted: boolean;
  updated_at: string;
}

export interface TxnPatchIn {
  book_id?: number | null;
  cat_id?: number | null;
  account_id?: number | null;
  kind?: TxnKind;
  amount_cents?: number;
  occurred_at?: string;
  note?: string;
}

export interface SummaryOut {
  month: string;
  out_cents: number;
  in_cents: number;
  left_cents: number;
  count: number;
  by_category: Array<{ name: string; cents: number }>;
  by_day: Record<string, number>;
}

export interface AiProfile {
  hints: string;
  version: number;
  feedback_count: number;
  updated_at: string | null;
}

export interface ImportResult {
  imported: number;
  skipped: number;
}

/** ---------------- 管理台（/admin） ---------------- */

export interface AdminUser {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  created_at: string;
  txns: number;
  books: number;
}

export interface AdminUserIn {
  username: string;
  pin: string;
  display_name: string;
  role: Role;
}

export interface AdminUserPatchIn {
  username?: string;
  display_name?: string;
  pin?: string;
  role?: Role;
}

export interface AdminUserPatchOut extends AdminUser {
  revoked_devices: number;
}

export interface AdminTxnPage {
  total: number;
  items: Txn[];
}

export interface AdminTxnIn {
  book_id?: number | null;
  cat_id?: number | null;
  account_id?: number | null;
  kind?: TxnKind;
  amount_cents?: number;
  occurred_at?: string | null;
  note?: string;
  source?: string;
}
