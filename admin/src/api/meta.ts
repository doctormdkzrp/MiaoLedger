import { del, get, patch, post } from "@/utils/http";
import type { Account, Book, Category, MeOut, MetaOut, TxnKind } from "./types";

/** 当前登录用户的概览计数。 */
export function fetchMe(): Promise<MeOut> {
  return get<MeOut>("/v1/me");
}

/** 账本 / 分类 / 账户。 */
export function fetchMeta(): Promise<MetaOut> {
  return get<MetaOut>("/v1/meta");
}

export function addBook(data: { name: string; icon?: string; sort?: number }): Promise<{ id: number; name: string }> {
  return post("/v1/books", { icon: "🏠", sort: 0, ...data }, { silent: true });
}

export function updateBook(
  bookId: number,
  data: { name: string; icon?: string; sort?: number }
): Promise<{ ok: boolean }> {
  return patch(`/v1/books/${bookId}`, { icon: "🏠", sort: 0, ...data }, { silent: true });
}

export function removeBook(bookId: number): Promise<{ ok: boolean }> {
  return del(`/v1/books/${bookId}`, { silent: true });
}

export function addAccount(data: {
  name: string;
  kind?: string;
  balance0_cents?: number;
  sort?: number;
}): Promise<{ id: number; name: string }> {
  return post("/v1/accounts", { kind: "virtual", balance0_cents: 0, sort: 0, ...data }, { silent: true });
}

export function addCategory(data: {
  name: string;
  parent_id?: number | null;
  kind?: TxnKind;
  icon?: string;
  sort?: number;
}): Promise<{ id: number; name: string }> {
  return post("/v1/categories", { parent_id: null, kind: "out", icon: "🏷", sort: 0, ...data }, { silent: true });
}

export function removeCategory(categoryId: number): Promise<{ ok: boolean }> {
  return del(`/v1/categories/${categoryId}`, { silent: true });
}

export type { Account, Book, Category, MeOut, MetaOut };
