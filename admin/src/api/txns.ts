import dayjs from "dayjs";
import { del, get, patch, post } from "@/utils/http";
import type { Txn, TxnKind } from "./types";

export interface TxnQuery {
  since?: string;
  book_id?: number | null;
  include_deleted?: boolean;
  limit?: number;
}

export interface MyTxnPayload {
  client_uuid: string;
  book_id?: number | null;
  cat_id?: number | null;
  account_id?: number | null;
  kind?: TxnKind;
  amount_cents: number;
  occurred_at: string;
  note?: string;
}

/** 拉取我的账单（后端返回数组，按 updated_at 升序，这里按发生时间倒序）。 */
export async function fetchTxns(query: TxnQuery = {}): Promise<Txn[]> {
  const rows = await get<Txn[]>("/v1/txns", {
    limit: query.limit ?? 2000,
    include_deleted: query.include_deleted ?? false,
    ...(query.since ? { since: query.since } : {}),
    ...(query.book_id != null ? { book_id: query.book_id } : {})
  });
  return sortByOccurred(rows);
}

export function sortByOccurred(rows: Txn[]): Txn[] {
  return [...rows].sort((a, b) => {
    const diff = dayjs(b.occurred_at).valueOf() - dayjs(a.occurred_at).valueOf();
    return diff !== 0 ? diff : b.id - a.id;
  });
}

export function patchTxn(clientUuid: string, data: Record<string, unknown>): Promise<Txn> {
  return patch<Txn>(`/v1/txns/${encodeURIComponent(clientUuid)}`, data, { silent: true });
}

export function removeTxn(clientUuid: string): Promise<{ ok: boolean }> {
  return del(`/v1/txns/${encodeURIComponent(clientUuid)}`, { silent: true });
}

/** 批量推送（新建 / 更新共用）。 */
export function pushTxns(txns: MyTxnPayload[]): Promise<{
  accepted: number;
  created: number;
  updated: number;
  server_time: string;
}> {
  return post("/v1/txns", { txns }, { silent: true });
}
