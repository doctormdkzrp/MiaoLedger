import dayjs from "dayjs";

/** 分 → 「12.34」字符串。 */
export function yuan(cents: number | null | undefined): string {
  const value = Number(cents || 0) / 100;
  return value.toFixed(2);
}

/** 分 → 「12.34 元」，用于卡片。 */
export function yuanWithUnit(cents: number | null | undefined): string {
  return `${yuan(cents)} 元`;
}

/** 「12.34」/「1,234」→ 分（整数）。不合法返回 NaN。 */
export function toCents(input: string | number): number {
  const text = String(input ?? "").replace(/,/g, "").trim();
  if (!text) return NaN;
  if (!/^-?\d+(\.\d{0,2})?$/.test(text)) return NaN;
  return Math.round(Number(text) * 100);
}

export function datetime(value: string | null | undefined): string {
  if (!value) return "-";
  const d = dayjs(value);
  return d.isValid() ? d.format("YYYY-MM-DD HH:mm") : String(value);
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "-";
  const d = dayjs(value);
  return d.isValid() ? d.format("YYYY-MM-DD") : String(value);
}

export function kindLabel(kind: string): string {
  if (kind === "in") return "收入";
  if (kind === "transfer") return "转账";
  return "支出";
}

export function kindTagType(kind: string): "success" | "danger" | "info" {
  if (kind === "in") return "success";
  if (kind === "transfer") return "info";
  return "danger";
}

export function roleLabel(role: string): string {
  return role === "admin" ? "管理员" : "普通用户";
}

/** 当月第一天 / 今天的 YYYY-MM-DD。 */
export function monthRange(month: string): { from: string; to: string } {
  const start = dayjs(`${month}-01`);
  return { from: start.format("YYYY-MM-DD"), to: start.endOf("month").format("YYYY-MM-DD") };
}

export function currentMonth(): string {
  return dayjs().format("YYYY-MM");
}
