import { get } from "@/utils/http";
import type { SummaryOut } from "./types";

/** 月度汇总（by_category / by_day 只统计支出）。 */
export function fetchSummary(month: string, bookId?: number | null): Promise<SummaryOut> {
  return get<SummaryOut>("/v1/summary", {
    month,
    ...(bookId != null ? { book_id: bookId } : {})
  });
}
