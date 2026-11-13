package com.miaoledger.data

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.google.gson.Gson
import com.google.gson.JsonObject
import java.util.concurrent.TimeUnit

/**
 * 备份：把手机上的账推一份到自己的服务器。
 * 手机才是主数据，服务器只是备份；所以备份失败不吵人，下次自己再试。
 */
object Sync {

    data class Result(
        val ok: Boolean,
        val pushed: Int,
        val learned: List<Learned> = emptyList(),
        val error: String? = null,
    )

    fun run(prefs: Prefs, db: LocalDb, api: Api): Result {
        if (!prefs.loggedIn) return Result(false, 0, error = "还没登录")
        return try {
            // 0) 上次在账号页清空了账单但没联网：先把服务器那份也清掉，别让旧账顺着 meta 又回来
            if (prefs.pendingWipe) {
                runCatching { api.wipeTxns() }.onSuccess { prefs.pendingWipe = false }
            }
            // 1) 先拿服务端的账本/分类/账户，新建分类后也能立刻用上
            api.syncMeta()
            // 2) 没备份过的账推上去
            val rows = db.unsynced()
            if (rows.isNotEmpty()) {
                api.push(rows)
                db.markSynced(rows.map { it.uuid })
            }
            // 3) 顺手把「AI 猜错了、我改了」的记录补传
            val learned = ArrayList<Learned>()
            val pending = db.pendingFeedback()
            if (pending.isNotEmpty()) {
                val sentIds = ArrayList<Long>()
                for ((id, payload) in pending) {
                    try {
                        learned += api.pushFeedback(payload)
                        sentIds.add(id)
                    } catch (e: ApiError) {
                        // 服务端还没升级 / 没网：留在队列里下次再传；其它错误丢掉，别一直堆着
                        if (!e.notDeployed && !e.offline) db.dropFeedback(id)
                    }
                }
                db.markFeedbackSent(sentIds)
            }
            if (learned.isNotEmpty()) {
                val last = learned.last()
                prefs.lastLearnAt = System.currentTimeMillis()
                prefs.lastLearned = when {
                    last.pattern.isNotBlank() && last.targetName.isNotBlank() -> "${last.pattern} → ${last.targetName}"
                    else -> last.targetName
                }
            }
            prefs.lastBackupAt = System.currentTimeMillis()
            Result(true, rows.size, learned)
        } catch (e: ApiError) {
            Result(false, 0, error = e.message)
        } catch (e: Exception) {
            Result(false, 0, error = e.message)
        }
    }

    /** 本机还没备份的笔数（含删除标记）。 */
    fun pendingCount(db: LocalDb): Int = db.countPending()
}

/** 后台自动备份。失败静默：不弹窗、不打断记账。 */
class BackupWorker(appContext: Context, params: WorkerParameters) : Worker(appContext, params) {
    override fun doWork(): Result {
        val prefs = Prefs(applicationContext)
        if (!prefs.loggedIn) return Result.success()
        val db = LocalDb(applicationContext)
        Sync.run(prefs, db, Api(prefs))
        return Result.success()
    }
}

object Backup {
    private const val PERIODIC = "miaoledger-backup-periodic"
    private const val NOW = "miaoledger-backup-now"
    private const val AFTER_SAVE = "miaoledger-backup-after-save"

    private fun online() = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /** 每 6 小时自动备份一次（系统会挑手机空闲的时候跑）。 */
    fun ensurePeriodic(ctx: Context) {
        runCatching {
            val req = PeriodicWorkRequestBuilder<BackupWorker>(6, TimeUnit.HOURS)
                .setConstraints(online())
                .build()
            WorkManager.getInstance(ctx)
                .enqueueUniquePeriodicWork(PERIODIC, ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }

    /** 打开 App / 点「现在备份」时马上备份一次。 */
    fun now(ctx: Context) {
        runCatching {
            val req = OneTimeWorkRequestBuilder<BackupWorker>()
                .setConstraints(online())
                .build()
            WorkManager.getInstance(ctx).enqueueUniqueWork(NOW, ExistingWorkPolicy.REPLACE, req)
        }
    }

    /** 记完一笔 30 秒后备份：刚记完常常还在同一页，等一会儿再传，别把刚记的落单。 */
    fun afterSave(ctx: Context) {
        runCatching {
            val req = OneTimeWorkRequestBuilder<BackupWorker>()
                .setInitialDelay(30, TimeUnit.SECONDS)
                .setConstraints(online())
                .build()
            WorkManager.getInstance(ctx).enqueueUniqueWork(AFTER_SAVE, ExistingWorkPolicy.REPLACE, req)
        }
    }
}

/** 把「AI 原先猜的」和「你最后改成啥」拼成一段反馈，排队等联网发。 */
object Feedback {
    private val gson = Gson()

    /**
     * 只有用户真的改过 AI 的分类/账户/账本才返回内容，否则返回 null（不用打扰服务器）。
     * newCategory 仅在「AI 建议了新建分类、用户同意了」时传。
     */
    fun correctionPayload(
        old: Txn?,
        newCatId: Long?,
        newAcctId: Long?,
        newBookId: Long?,
        kind: String,
        cents: Long,
        note: String,
        newCategory: JsonObject? = null,
    ): String? {
        if (old == null || old.source != "ai") return null
        // 没存下 AI 当时的原话就学不了（服务端要求 text 非空，拿它提关键词），别白传一条 422
        val said = old.aiText?.trim().orEmpty()
        if (said.isEmpty()) return null
        val pCat = old.parsedCatId ?: old.catId
        val pAcct = old.parsedAcctId ?: old.acctId
        val pBook = old.parsedBookId ?: old.bookId
        val changed = pCat != newCatId || pAcct != newAcctId || pBook != newBookId
        if (!changed) return null
        val parsed = JsonObject().apply {
            addProperty("kind", old.kind)
            pCat?.let { addProperty("cat_id", it) }
            pAcct?.let { addProperty("account_id", it) }
            pBook?.let { addProperty("book_id", it) }
        }
        val fin = JsonObject().apply {
            newCatId?.let { addProperty("cat_id", it) }
            newAcctId?.let { addProperty("account_id", it) }
            newBookId?.let { addProperty("book_id", it) }
            addProperty("kind", kind)
            addProperty("amount_cents", cents)
            addProperty("note", note)
        }
        val body = JsonObject().apply {
            addProperty("text", said)
            addProperty("note", old.note)
            add("parsed", parsed)
            add("final", fin)
            if (newCategory != null) add("new_category", newCategory)
        }
        return gson.toJson(body)
    }

    /** 用户同意 AI 的建议、新建了一个分类时，告诉服务端这个名字和图标。 */
    fun newCategory(name: String, kind: String, icon: String): JsonObject = JsonObject().apply {
        addProperty("name", name)
        addProperty("kind", kind)
        addProperty("icon", icon)
    }
}
