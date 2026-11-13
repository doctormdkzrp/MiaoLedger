package com.miaoledger.data

import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * 把手机本地库导成 CSV（Excel 直接能打开）。
 * 全部在本地生成，不依赖服务器：账是手机上的，导一份自己留着不需要联网。
 */
object CsvExport {

    private const val BOM = "\uFEFF"

    fun defaultName(): String =
        "账单-" + LocalDate.now().format(DateTimeFormatter.ofPattern("yyyyMMdd")) + ".csv"

    private fun esc(s: String): String {
        val need = s.any { it == ',' || it == '"' || it == '\n' || it == '\r' }
        return if (need) "\"" + s.replace("\"", "\"\"") + "\"" else s
    }

    private fun srcCn(s: String): String = when (s) {
        "manual" -> "手动"
        "ai" -> "语音"
        "import" -> "导入"
        else -> s.ifBlank { "手动" }
    }

    fun build(
        txns: List<Txn>,
        cats: List<Cat> = emptyList(),
        accts: List<Acct> = emptyList(),
        books: List<Book> = emptyList(),
    ): String {
        val catName = cats.associate { it.id to it.name }
        val acctName = accts.associate { it.id to it.name }
        val bookName = books.associate { it.id to it.name }
        val sb = StringBuilder(BOM)
        sb.append("日期,时间,类型,金额,分类,账户,账本,备注,来源\r\n")
        txns.filter { !it.deleted }.sortedByDescending { it.at }.forEach { t ->
            val time = LocalDateTime.ofInstant(Instant.ofEpochMilli(t.at), ZoneId.systemDefault())
            val d = time.toLocalDate()
            val amount = String.format(java.util.Locale.US, "%.2f", t.cents / 100.0)
            val kind = if (t.kind == "in") "收入" else "支出"
            sb.append(
                listOf(
                    "${d.year}-%02d-%02d".format(d.monthValue, d.dayOfMonth),
                    "%02d:%02d".format(time.hour, time.minute),
                    kind,
                    amount,
                    catName[t.catId ?: -1L] ?: "其它",
                    acctName[t.acctId ?: -1L] ?: "",
                    bookName[t.bookId ?: -1L] ?: "",
                    t.note,
                    srcCn(t.source),
                ).joinToString(",") { esc(it) }
            )
            sb.append("\r\n")
        }
        return sb.toString()
    }
}
