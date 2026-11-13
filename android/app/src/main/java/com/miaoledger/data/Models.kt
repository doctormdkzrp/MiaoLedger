package com.miaoledger.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.util.UUID

data class Book(val id: Long, val name: String, val icon: String = "🏠")
data class Cat(val id: Long, val name: String, val kind: String = "out", val icon: String = "🏷")
data class Acct(val id: Long, val name: String, val kind: String = "virtual")

data class Txn(
    val uuid: String,
    val bookId: Long?,
    val catId: Long?,
    val acctId: Long?,
    val kind: String,          // out / in / transfer
    val cents: Long,
    val at: Long,              // epoch millis
    val note: String,
    val source: String = "manual",
    val synced: Boolean = false,
    val deleted: Boolean = false,
    // AI 记的那一笔，最初被分到哪（用户后来改了，就用来告诉 AI 纠正了什么）
    val parsedCatId: Long? = null,
    val parsedAcctId: Long? = null,
    val parsedBookId: Long? = null,
    val aiText: String? = null,
)

/** 本机配置：服务器地址、token、上次用的账本/账户。 */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("miaoledger", Context.MODE_PRIVATE)
    private val gson = Gson()

    var server: String
        get() = sp.getString("server", "") ?: ""
        set(v) = sp.edit().putString("server", v).apply()
    var token: String
        get() = sp.getString("token", "") ?: ""
        set(v) = sp.edit().putString("token", v).apply()
    var username: String
        get() = sp.getString("username", "") ?: ""
        set(v) = sp.edit().putString("username", v).apply()
    var displayName: String
        get() = sp.getString("display", "") ?: ""
        set(v) = sp.edit().putString("display", v).apply()
    var bookId: Long
        get() = sp.getLong("bookId", 0L)
        set(v) = sp.edit().putLong("bookId", v).apply()
    var lastAcctId: Long
        get() = sp.getLong("lastAcct", 0L)
        set(v) = sp.edit().putLong("lastAcct", v).apply()
    var lastPullAt: Long
        get() = sp.getLong("lastPull", 0L)
        set(v) = sp.edit().putLong("lastPull", v).apply()

    /** 上次备份成功的时间（0 = 还没备份过）。 */
    var lastBackupAt: Long
        get() = sp.getLong("lastBackup", 0L)
        set(v) = sp.edit().putLong("lastBackup", v).apply()

    /** 最近一次 AI 从你的修改里学到东西的时间。 */
    var lastLearnAt: Long
        get() = sp.getLong("lastLearn", 0L)
        set(v) = sp.edit().putLong("lastLearn", v).apply()

    /** 最近学到的那条规律，说人话，例如「Open Code → AI 研究」。 */
    var lastLearned: String
        get() = sp.getString("lastLearned", "") ?: ""
        set(v) = sp.edit().putString("lastLearned", v).apply()

    /** 用户清空了账单但当时没联网：下次备份前先把服务器上那份也清掉。 */
    var pendingWipe: Boolean
        get() = sp.getBoolean("pendingWipe", false)
        set(v) = sp.edit().putBoolean("pendingWipe", v).apply()

    var books: List<Book>
        get() = gson.fromJson(sp.getString("books", "[]"), object : TypeToken<List<Book>>() {}.type) ?: emptyList()
        set(v) = sp.edit().putString("books", gson.toJson(v)).apply()
    var cats: List<Cat>
        get() = gson.fromJson(sp.getString("cats", "[]"), object : TypeToken<List<Cat>>() {}.type) ?: emptyList()
        set(v) = sp.edit().putString("cats", gson.toJson(v)).apply()
    var accts: List<Acct>
        get() = gson.fromJson(sp.getString("accts", "[]"), object : TypeToken<List<Acct>>() {}.type) ?: emptyList()
        set(v) = sp.edit().putString("accts", gson.toJson(v)).apply()

    val loggedIn: Boolean get() = token.isNotEmpty() && server.isNotEmpty()
}

/** 本地库：账单只存这里，服务器是备份。synced=0 表示还没推上去。 */
class LocalDb(ctx: Context) : SQLiteOpenHelper(ctx, "miaoledger.db", null, 2) {

    private fun createTxns(db: SQLiteDatabase) {
        db.execSQL(
            """create table if not exists txns(
                uuid text primary key,
                book_id integer, cat_id integer, acct_id integer,
                kind text not null, cents integer not null, at integer not null,
                note text, source text, synced integer not null default 0,
                deleted integer not null default 0,
                parsed_cat_id integer, parsed_acct_id integer, parsed_book_id integer,
                ai_text text)"""
        )
        db.execSQL("create index if not exists ix_txns_at on txns(at)")
    }

    /** AI 纠正队列：用户改了 AI 的分类/账户，先把「改了什么」存下来，联网再告诉服务器。 */
    private fun createFeedback(db: SQLiteDatabase) {
        db.execSQL(
            """create table if not exists ai_feedback(
                id integer primary key autoincrement,
                payload text not null,
                created_at integer not null default 0,
                sent integer not null default 0)"""
        )
        db.execSQL("create index if not exists ix_ai_feedback_sent on ai_feedback(sent)")
    }

    override fun onCreate(db: SQLiteDatabase) {
        createTxns(db)
        createFeedback(db)
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            // 老库的 txns 少了 AI 那几列；加过就跳过
            listOf(
                "alter table txns add column parsed_cat_id integer",
                "alter table txns add column parsed_acct_id integer",
                "alter table txns add column parsed_book_id integer",
                "alter table txns add column ai_text text",
            ).forEach { sql -> runCatching { db.execSQL(sql) } }
            runCatching { createFeedback(db) }
        }
    }

    fun newUuid(): String = UUID.randomUUID().toString().replace("-", "")

    fun upsertLocal(t: Txn) {
        val v = android.content.ContentValues().apply {
            put("uuid", t.uuid); put("book_id", t.bookId); put("cat_id", t.catId); put("acct_id", t.acctId)
            put("kind", t.kind); put("cents", t.cents); put("at", t.at); put("note", t.note)
            put("source", t.source); put("synced", if (t.synced) 1 else 0); put("deleted", if (t.deleted) 1 else 0)
            put("parsed_cat_id", t.parsedCatId); put("parsed_acct_id", t.parsedAcctId)
            put("parsed_book_id", t.parsedBookId); put("ai_text", t.aiText)
        }
        writableDatabase.insertWithOnConflict("txns", null, v, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun all(): List<Txn> {
        val out = ArrayList<Txn>()
        readableDatabase.rawQuery("select * from txns where deleted=0 order by at desc", null).use { c ->
            while (c.moveToNext()) out.add(read(c))
        }
        return out
    }

    fun unsynced(): List<Txn> {
        val out = ArrayList<Txn>()
        readableDatabase.rawQuery("select * from txns where synced=0", null).use { c ->
            while (c.moveToNext()) out.add(read(c))
        }
        return out
    }

    fun softDelete(uuid: String) {
        writableDatabase.execSQL("update txns set deleted=1, synced=0 where uuid=?", arrayOf<Any>(uuid))
    }

    fun byUuid(uuid: String): Txn? {
        readableDatabase.rawQuery("select * from txns where uuid=?", arrayOf(uuid)).use { c ->
            return if (c.moveToFirst()) read(c) else null
        }
    }

    fun markSynced(uuids: List<String>) {
        if (uuids.isEmpty()) return
        val inClause = uuids.joinToString(",") { "'$it'" }
        writableDatabase.execSQL("update txns set synced=1 where uuid in ($inClause)")
    }

    fun countPending(): Int =
        readableDatabase.rawQuery("select count(*) from txns where synced=0", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    /** 本地一共多少笔（不含删除标记）——「清空所有账单」前给用户看的数字。 */
    fun countAll(): Int =
        readableDatabase.rawQuery("select count(*) from txns where deleted=0", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    /** 清空本机所有账单（含删除标记和 AI 纠正队列）。服务器那份由 pendingWipe 交给备份补做。 */
    fun deleteAll() {
        runCatching { writableDatabase.execSQL("delete from txns") }
        runCatching { writableDatabase.execSQL("delete from ai_feedback") }
    }

    // ---------------------------------------------------------------- AI 纠正队列
    fun enqueueFeedback(payload: String): Long {
        val v = android.content.ContentValues().apply {
            put("payload", payload)
            put("created_at", System.currentTimeMillis())
            put("sent", 0)
        }
        return writableDatabase.insert("ai_feedback", null, v)
    }

    fun pendingFeedback(limit: Int = 20): List<Pair<Long, String>> {
        val out = ArrayList<Pair<Long, String>>()
        readableDatabase.rawQuery(
            "select id, payload from ai_feedback where sent=0 order by id limit $limit", null
        ).use { c ->
            while (c.moveToNext()) out.add(c.getLong(0) to c.getString(1))
        }
        return out
    }

    fun markFeedbackSent(ids: List<Long>) {
        if (ids.isEmpty()) return
        val inClause = ids.joinToString(",")
        writableDatabase.execSQL("update ai_feedback set sent=1 where id in ($inClause)")
    }

    /** 服务端明确不收（不是网络问题）就丢掉，别一直堆着。 */
    fun dropFeedback(id: Long) {
        writableDatabase.execSQL("delete from ai_feedback where id=?", arrayOf<Any>(id))
    }

    fun countFeedbackPending(): Int =
        readableDatabase.rawQuery("select count(*) from ai_feedback where sent=0", null).use { c ->
            if (c.moveToFirst()) c.getInt(0) else 0
        }

    private fun col(c: android.database.Cursor, name: String): Int = c.getColumnIndex(name)

    private fun read(c: android.database.Cursor): Txn {
        val iCat = col(c, "cat_id"); val iAcct = col(c, "acct_id"); val iBook = col(c, "book_id")
        val iNote = col(c, "note"); val iSrc = col(c, "source")
        val iParsedCat = col(c, "parsed_cat_id"); val iParsedAcct = col(c, "parsed_acct_id")
        val iParsedBook = col(c, "parsed_book_id"); val iText = col(c, "ai_text")
        fun lngOrNull(i: Int): Long? =
            if (i < 0 || c.isNull(i)) null else c.getLong(i).takeIf { it > 0 }
        fun txtOrNull(i: Int): String? =
            if (i < 0 || c.isNull(i)) null else c.getString(i)?.takeIf { it.isNotBlank() }
        return Txn(
            uuid = c.getString(c.getColumnIndexOrThrow("uuid")),
            bookId = lngOrNull(iBook),
            catId = lngOrNull(iCat),
            acctId = lngOrNull(iAcct),
            kind = c.getString(c.getColumnIndexOrThrow("kind")),
            cents = c.getLong(c.getColumnIndexOrThrow("cents")),
            at = c.getLong(c.getColumnIndexOrThrow("at")),
            note = if (iNote >= 0 && !c.isNull(iNote)) c.getString(iNote) ?: "" else "",
            source = if (iSrc >= 0 && !c.isNull(iSrc)) c.getString(iSrc) ?: "manual" else "manual",
            synced = c.getInt(c.getColumnIndexOrThrow("synced")) == 1,
            deleted = c.getInt(c.getColumnIndexOrThrow("deleted")) == 1,
            parsedCatId = lngOrNull(iParsedCat),
            parsedAcctId = lngOrNull(iParsedAcct),
            parsedBookId = lngOrNull(iParsedBook),
            aiText = txtOrNull(iText),
        )
    }
}
