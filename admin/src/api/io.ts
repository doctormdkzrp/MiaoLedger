import { download, upload } from "@/utils/http";
import type { ImportResult } from "./types";

/** CSV 表头口径（8 列，和后端 common.export_csv_text 一致）。 */
export const CSV_HEADER = ["时间", "金额", "收支", "分类", "资产账户", "账本", "货币", "备注"] as const;

/** 导出我的账单为 CSV（带 token 拉 blob 再保存）。 */
export function exportMyCsv(from: string, to: string, bookId?: number | null): Promise<void> {
  return download(
    "/v1/export.csv",
    { from, to, ...(bookId != null ? { book_id: bookId } : {}) },
    `小喵记账-${from}_${to}.csv`
  );
}

/** 导入 8 列 CSV。 */
export function importMyCsv(file: File): Promise<ImportResult> {
  return upload<ImportResult>("/v1/import/csv", file);
}
