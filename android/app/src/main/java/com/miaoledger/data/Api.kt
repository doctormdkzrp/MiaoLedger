package com.miaoledger.data

import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonPrimitive
import com.google.gson.reflect.TypeToken
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * 出错时抛这个，带「人话」提示。code=0 表示根本没连上（网络/地址不对），
 * code=404 表示服务端还没升级到会这个功能的那一版。
 */
class ApiError(
    val code: Int,
    val detail: String? = null,
    cause: Throwable? = null,
) : Exception(humanMessage(code, detail), cause) {
    val offline: Boolean get() = code == 0
    val notDeployed: Boolean get() = code == 404
}

/** 把服务端的报错翻译成普通用户能看懂的话。 */
fun humanMessage(code: Int, detail: String? = null): String {
    val d = detail?.trim()?.takeIf { it.isNotEmpty() }
    return when (code) {
        0 -> "连不上服务器。检查一下手机网络，或者服务器地址填得对不对，然后再试一次。"
        401 -> "账号或密码不对。密码是数字，输错了就再输一遍。"
        403 -> "邀请码不对。向已经在用这个 App 的人要一下邀请码。"
        404 -> "服务器还没升级到这一版，这个功能暂时用不了。等它更新完再试。"
        409 -> "这个账号名已经有人用了，换一个再试。"
        422 -> d ?: "填的内容格式不太对，检查一下再试。"
        in 500..599 -> "服务器出了点小问题，过一会儿再试。"
        else -> d ?: "出了点小问题（编号 $code），过一会儿再试。"
    }
}

data class UsernameCheck(val available: Boolean, val reason: String? = null)

data class Learned(val kind: String, val pattern: String, val targetName: String)

data class AiRule(
    val id: Long,
    val kind: String,
    val pattern: String,
    val targetName: String,
    val weight: Double,
    val hits: Int,
    val updatedAt: String,
)

data class AiProfile(val hints: String, val version: String, val updatedAt: String)

/** AI 记忆页要的东西：提示词、它怎么认账、对你的印象、记住的规矩、统计。 */
data class AiMemory(
    val prompt: String = "",
    val how: String = "",
    val hints: String = "",
    val rules: List<AiRule> = emptyList(),
    val rulesCount: Int = 0,
    val feedbackCount: Int = 0,
    val version: String = "",
    val updatedAt: String = "",
)

/**
 * 和服务端说话的地方。所有请求都带 Bearer token；服务器按 token 的用户过滤数据。
 * 网络不通时抛 ApiError，调用方负责"离线也能记"的兜底（本地先落库，队列补传）。
 */
class Api(private val prefs: Prefs) {

    private val gson = Gson()
    private val json = "application/json; charset=utf-8".toMediaType()
    private val client = OkHttpClient.Builder()
        .connectTimeout(6, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    private fun url(path: String) = prefs.server.trimEnd('/') + path

    private fun req(path: String, body: String? = null, method: String = "GET", auth: Boolean = true): Request {
        val b = Request.Builder().url(url(path))
        if (auth && prefs.token.isNotEmpty()) b.header("Authorization", "Bearer ${prefs.token}")
        if (body != null) b.method(method, body.toRequestBody(json)) else b.method(method, null)
        return b.build()
    }

    /** 服务端报错体是 {"detail": "中文"}；也兼容 detail 是数组/对象的情况。 */
    private fun detailOf(text: String): String? = runCatching {
        val o = gson.fromJson(text, JsonObject::class.java)
        val d = o.get("detail") ?: return@runCatching null
        when {
            d.isJsonPrimitive -> d.asString
            d.isJsonArray -> d.asJsonArray.joinToString("；") { it.toString().trim('"') }
            else -> null
        }
    }.getOrNull()

    private fun exec(r: Request): String {
        val res = try {
            client.newCall(r).execute()
        } catch (e: java.io.IOException) {
            throw ApiError(0, null, e)
        }
        res.use {
            val text = it.body?.string().orEmpty()
            if (!it.isSuccessful) throw ApiError(it.code, detailOf(text))
            return text
        }
    }

    private fun applyToken(o: JsonObject) {
        prefs.token = o.get("token")?.takeIf { !it.isJsonNull }?.asString ?: ""
        prefs.username = o.get("username")?.takeIf { !it.isJsonNull }?.asString ?: ""
        prefs.displayName = o.get("display_name")?.takeIf { !it.isJsonNull }?.asString ?: prefs.username
    }

    fun login(server: String, username: String, pin: String, device: String = "android"): Boolean {
        val body = gson.toJson(mapOf("username" to username, "pin" to pin, "device_name" to device))
        prefs.server = server
        val text = exec(req("/api/v1/auth/login", body, "POST", auth = false))
        applyToken(gson.fromJson(text, JsonObject::class.java))
        return true
    }

    fun register(server: String, username: String, pin: String, code: String, display: String): Boolean {
        prefs.server = server
        val body = gson.toJson(
            mapOf("username" to username, "pin" to pin, "invite_code" to code, "display_name" to display, "device_name" to "android")
        )
        val text = exec(req("/api/v1/auth/register", body, "POST", auth = false))
        applyToken(gson.fromJson(text, JsonObject::class.java))
        return true
    }

    /** 注册第二步：账号名能不能用。服务端没这个接口（404）时抛 ApiError(404)，界面就放行。 */
    fun checkUsername(username: String): UsernameCheck {
        val q = java.net.URLEncoder.encode(username, "UTF-8")
        val o = gson.fromJson(
            exec(req("/api/v1/auth/check-username?username=$q", null, "GET", auth = false)),
            JsonObject::class.java,
        )
        return UsernameCheck(
            available = o.get("available")?.takeIf { !it.isJsonNull }?.asBoolean ?: true,
            reason = o.get("reason")?.takeIf { !it.isJsonNull }?.asString,
        )
    }

    /** 退出登录：顺手让服务端把当前设备的登录作废（失败也不影响本地退出）。 */
    fun logout(): Boolean = runCatching {
        exec(req("/api/v1/auth/logout", "{}", "POST"))
        true
    }.getOrDefault(false)

    /** 拉账本/分类/账户，缓存到本地。 */
    fun syncMeta() {
        val o = gson.fromJson(exec(req("/api/v1/meta")), JsonObject::class.java)
        val bookType = object : TypeToken<List<Book>>() {}.type
        val catType = object : TypeToken<List<Cat>>() {}.type
        val acctType = object : TypeToken<List<Acct>>() {}.type
        prefs.books = gson.fromJson(o.getAsJsonArray("books"), bookType) ?: emptyList()
        prefs.cats = gson.fromJson(o.getAsJsonArray("categories"), catType) ?: emptyList()
        prefs.accts = gson.fromJson(o.getAsJsonArray("accounts"), acctType) ?: emptyList()
        if (prefs.bookId == 0L) prefs.books.firstOrNull()?.let { prefs.bookId = it.id }
        if (prefs.lastAcctId == 0L) prefs.accts.firstOrNull()?.let { prefs.lastAcctId = it.id }
    }

    /** 新建账本，返回新账本 id。 */
    fun createBook(name: String, icon: String = "📒"): Long {
        val body = gson.toJson(mapOf("name" to name, "icon" to icon, "sort" to 0))
        val o = gson.fromJson(exec(req("/api/v1/books", body, "POST")), JsonObject::class.java)
        return o.get("id").asLong
    }

    /** 新建分类（AI 建议的那个分类），返回新分类 id。重名会抛 ApiError(409)。 */
    fun createCategory(name: String, kind: String = "out", icon: String = "🏷"): Long {
        val body = gson.toJson(mapOf("name" to name, "kind" to kind, "icon" to icon, "sort" to 0))
        val o = gson.fromJson(exec(req("/api/v1/categories", body, "POST")), JsonObject::class.java)
        return o.get("id").asLong
    }

    fun push(txns: List<Txn>): Int {
        if (txns.isEmpty()) return 0
        val arr = txns.map {
            mapOf(
                "client_uuid" to it.uuid,
                "book_id" to it.bookId,
                "cat_id" to it.catId,
                "account_id" to it.acctId,
                "kind" to it.kind,
                "amount_cents" to it.cents,
                "occurred_at" to java.time.Instant.ofEpochMilli(it.at).toString(),
                "note" to it.note,
                "source" to it.source,
                "deleted" to it.deleted,
            )
        }
        val body = gson.toJson(mapOf("txns" to arr))
        exec(req("/api/v1/txns", body, "POST"))
        return txns.size
    }

    /** 告诉服务端「AI 这次猜错了，我改成了这样」。payload 是本地排队时存下的整段 JSON。 */
    fun pushFeedback(payload: String): List<Learned> {
        val text = exec(req("/api/v1/ai/feedback", payload, "POST"))
        val o = runCatching { gson.fromJson(text, JsonObject::class.java) }.getOrNull() ?: return emptyList()
        val arr: JsonArray = o.getAsJsonArray("learned") ?: return emptyList()
        return arr.mapNotNull { el ->
            runCatching {
                val j = el.asJsonObject
                Learned(
                    kind = j.get("kind")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    pattern = j.get("pattern")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    targetName = j.get("target_name")?.takeIf { !it.isJsonNull }?.asString ?: "",
                )
            }.getOrNull()
        }
    }

    /** AI 记住的规律（「它的记忆」页用）。服务端没升级会抛 ApiError(404)。 */
    fun rules(): List<AiRule> {
        val o = gson.fromJson(exec(req("/api/v1/ai/rules")), JsonObject::class.java)
        return rulesOf(o.getAsJsonArray("rules"))
    }

    private fun rulesOf(arr: JsonArray?): List<AiRule> {
        if (arr == null) return emptyList()
        return arr.mapNotNull { el ->
            runCatching {
                val j = el.asJsonObject
                AiRule(
                    id = j.get("id")?.takeIf { !it.isJsonNull }?.asLong ?: return@runCatching null,
                    kind = j.get("kind")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    pattern = j.get("pattern")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    targetName = j.get("target_name")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    weight = j.get("weight")?.takeIf { !it.isJsonNull }?.asDouble ?: 0.0,
                    hits = j.get("hits")?.takeIf { !it.isJsonNull }?.asInt ?: 0,
                    updatedAt = j.get("updated_at")?.takeIf { !it.isJsonNull }?.asString ?: "",
                )
            }.getOrNull()
        }
    }

    /** 「它的记忆」：一次拿到提示词/说明/印象/规矩/统计。服务端没这个接口时返回 null（调用方回退到 rules+profile）。 */
    fun aiMemory(): AiMemory? {
        val text = try {
            exec(req("/api/v1/ai/memory"))
        } catch (e: ApiError) {
            if (e.notDeployed) return null else throw e
        }
        val o = runCatching { gson.fromJson(text, JsonObject::class.java) }.getOrNull() ?: return null
        fun txt(k: String): String {
            val e = o.get(k) ?: return ""
            if (e.isJsonNull) return ""
            return runCatching {
                when {
                    e.isJsonArray -> e.asJsonArray.mapNotNull { v -> if (v.isJsonPrimitive) v.asString else v.toString() }
                        .joinToString("；")
                    e.isJsonObject -> e.toString()
                    else -> e.asString
                }
            }.getOrDefault(e.toString())
        }
        val stats = o.getAsJsonObject("stats")
        fun statInt(k: String): Int = runCatching {
            stats?.get(k)?.takeIf { !it.isJsonNull }?.asInt ?: 0
        }.getOrDefault(0)
        fun statTxt(k: String): String = runCatching {
            stats?.get(k)?.takeIf { !it.isJsonNull }?.asString ?: ""
        }.getOrDefault("")
        val list = rulesOf(o.getAsJsonArray("rules"))
        return AiMemory(
            prompt = txt("prompt"),
            how = txt("how"),
            hints = txt("hints"),
            rules = list,
            rulesCount = if (stats != null) statInt("rules") else list.size,
            feedbackCount = statInt("feedback_count"),
            version = statTxt("version").ifBlank { txt("version") },
            updatedAt = statTxt("updated_at"),
        )
    }

    /** 改密码。返回被踢下线的设备数（0 = 只有当前这台在用）。旧密码不对抛 401，新密码不合规抛 422。 */
    fun changePin(old: String, new: String): Int {
        val body = gson.toJson(mapOf("old_pin" to old, "new_pin" to new))
        val o = gson.fromJson(exec(req("/api/v1/auth/change-pin", body, "POST")), JsonObject::class.java)
        return o.get("revoked_devices")?.takeIf { !it.isJsonNull }?.asInt ?: 0
    }

    /** 把服务器上那份账单全清掉（软删），返回清了多少笔。 */
    fun wipeTxns(): Int {
        val o = gson.fromJson(exec(req("/api/v1/txns/all", null, "DELETE")), JsonObject::class.java)
        return o.get("deleted")?.takeIf { !it.isJsonNull }?.asInt ?: 0
    }

    fun deleteCategory(id: Long) {
        exec(req("/api/v1/categories/$id", null, "DELETE"))
    }

    fun profile(): AiProfile {
        val o = gson.fromJson(exec(req("/api/v1/ai/profile")), JsonObject::class.java)
        // hints 可能是字符串，也可能是字符串数组；version 可能是数字，统一转成能显示的字符串，别因为类型不同就崩
        fun anyText(k: String): String {
            val e = o.get(k) ?: return ""
            if (e.isJsonNull) return ""
            return runCatching {
                when {
                    e.isJsonArray -> e.asJsonArray.mapNotNull { it?.let { v -> if (v.isJsonPrimitive) v.asString else v.toString() } }.joinToString("；")
                    e.isJsonObject -> e.toString()
                    else -> e.asString
                }
            }.getOrDefault(e.toString())
        }
        return AiProfile(
            hints = anyText("hints"),
            version = anyText("version"),
            updatedAt = anyText("updated_at"),
        )
    }

    fun deleteRule(id: Long) {
        exec(req("/api/v1/ai/rules/$id", null, "DELETE"))
    }

    /** 按住说话的 wav 传给服务端，走火山引擎识别成文字。 */
    fun asr(wav: ByteArray): String {
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", "voice.wav", wav.toRequestBody("audio/wav".toMediaType()))
            .build()
        val r = Request.Builder().url(url("/api/v1/asr"))
            .header("Authorization", "Bearer ${prefs.token}")
            .post(body)
            .build()
        val o = gson.fromJson(exec(r), JsonObject::class.java)
        return o.get("text")?.takeIf { !it.isJsonNull }?.asString ?: ""
    }

    /** 服务端软删一笔（本地已经先标 deleted）。 */
    fun deleteTxn(uuid: String) {
        exec(req("/api/v1/txns/$uuid", null, "DELETE"))
    }

    data class ParseResult(
        val ok: Boolean,
        val kind: String,
        val cents: Long?,
        val catId: Long?,
        val catName: String?,
        val acctId: Long?,
        val acctName: String?,
        val bookId: Long?,
        val bookName: String?,
        val note: String,
        val at: Long,
        val confidence: Double,
        val needs: List<String>,
        val engine: String?,
        // AI 觉得这笔该进一个还不存在的分类时，给出名字/类型/图标
        val suggestName: String? = null,
        val suggestKind: String = "out",
        val suggestIcon: String = "🏷",
        // AI 这次顺便学会的一条规律，例如「Open Code → AI 研究」
        val learnedRule: String? = null,
    )

    fun parse(text: String): ParseResult {
        val body = gson.toJson(mapOf("text" to text))
        val o = gson.fromJson(exec(req("/api/v1/ai/parse", body, "POST")), JsonObject::class.java)
        fun lng(k: String): Long? = o.get(k)?.takeIf { !it.isJsonNull }?.asLong
        fun str(k: String): String? = o.get(k)?.takeIf { !it.isJsonNull }?.let { if (it is JsonPrimitive) it.asString else null }
        val at = o.get("occurred_at")?.takeIf { !it.isJsonNull }?.asString
            ?.let { runCatching { java.time.LocalDateTime.parse(it).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli() }.getOrNull() }
            ?: System.currentTimeMillis()
        val raw = o.getAsJsonObject("raw")
        val suggest = o.getAsJsonObject("suggest_category")
        val learnedRaw = raw?.get("learned_rule")
        val learned = when {
            learnedRaw == null || learnedRaw.isJsonNull -> null
            learnedRaw.isJsonPrimitive -> learnedRaw.asString.takeIf { it.isNotBlank() }
            learnedRaw.isJsonArray -> learnedRaw.asJsonArray
                .mapNotNull { runCatching { it.asString }.getOrNull() }
                .takeIf { it.isNotEmpty() }?.joinToString("、")
            else -> null
        }
        return ParseResult(
            ok = o.get("ok")?.takeIf { !it.isJsonNull }?.asBoolean ?: false,
            kind = o.get("kind")?.takeIf { !it.isJsonNull }?.asString ?: "out",
            cents = lng("amount_cents"),
            catId = lng("cat_id"),
            catName = str("cat_name"),
            acctId = lng("account_id"),
            acctName = str("account_name"),
            bookId = lng("book_id"),
            bookName = str("book_name"),
            note = o.get("note")?.takeIf { !it.isJsonNull }?.asString ?: text,
            at = at,
            confidence = o.get("confidence")?.takeIf { !it.isJsonNull }?.asDouble ?: 0.0,
            needs = gson.fromJson(o.getAsJsonArray("needs"), object : TypeToken<List<String>>() {}.type) ?: emptyList(),
            engine = raw?.get("engine")?.takeIf { !it.isJsonNull }?.asString,
            suggestName = suggest?.get("name")?.takeIf { !it.isJsonNull }?.asString,
            suggestKind = suggest?.get("kind")?.takeIf { !it.isJsonNull }?.asString ?: "out",
            suggestIcon = suggest?.get("icon")?.takeIf { !it.isJsonNull }?.asString ?: "🏷",
            learnedRule = learned,
        )
    }

    fun summary(month: String): JsonObject =
        gson.fromJson(exec(req("/api/v1/summary?month=$month")), JsonObject::class.java)

    fun health(): Boolean = runCatching { exec(req("/health", auth = false)); true }.getOrDefault(false)
}
