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
 *
 * bizCode 是服务端报错体里的 code 字段（例如 DEVICE_PENDING / DEVICE_REVOKED）。
 * 光看 HTTP 状态码分不出来是「邀请码不对」还是「这台手机没批」，所以要把 body 里的
 * code 也带出来，文案才能对应上。
 */
class ApiError(
    val code: Int,
    val detail: String? = null,
    cause: Throwable? = null,
    val bizCode: String? = null,
) : Exception(humanMessage(code, detail, bizCode), cause) {
    val offline: Boolean get() = code == 0
    val notDeployed: Boolean get() = code == 404
    val devicePending: Boolean get() = bizCode == "DEVICE_PENDING"
    val deviceRevoked: Boolean get() = bizCode == "DEVICE_REVOKED"
}

/** 把服务端的报错翻译成普通用户能看懂的话。 */
fun humanMessage(code: Int, detail: String? = null, bizCode: String? = null): String {
    val d = detail?.trim()?.takeIf { it.isNotEmpty() }
    return when (code) {
        0 -> "连不上服务器。检查一下手机网络，或者服务器地址填得对不对，然后再试一次。"
        401 -> "账号或密码不对。密码是数字，输错了就再输一遍。"
        // 403 有两种意思，必须按服务端给的 code 分开说，否则「设备没批」会被说成「邀请码不对」
        403 -> when (bizCode) {
            "DEVICE_PENDING" -> "这台手机还没被批准，让管服务器的人在后台点一下。"
            "DEVICE_REVOKED" -> "这台手机已经被停用了。要重新用，让管服务器的人在后台批一下。"
            else -> "邀请码不对。向已经在用这个 App 的人要一下邀请码。"
        }
        429 -> d ?: "操作太频繁了，过一会儿再试。"
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
        // 每台设备带一个自己生成的指纹，服务端靠它判断这台机器批没批（见 auth.device_for_login）
        b.header("X-Device-Id", prefs.deviceId)
        b.header("X-Device-Name", deviceName())
        if (body != null) b.method(method, body.toRequestBody(json)) else b.method(method, null)
        return b.build()
    }

    /** 设备名只用来在管理台里认出「哪个是我妈的手机」，取手机型号就够。 */
    private fun deviceName(): String =
        (android.os.Build.MODEL ?: "").trim().ifEmpty { "android" }.take(64)

    /** 服务端报错体是 {"detail": "中文", "code": "DEVICE_PENDING"}；detail 也可能是数组/对象。 */
    private fun jsonOf(text: String): JsonObject? = runCatching {
        gson.fromJson(text, JsonObject::class.java)
    }.getOrNull()

    private fun detailOf(text: String): String? {
        val od = jsonOf(text) ?: return null
        val d = od.get("detail") ?: return null
        return when {
            d.isJsonPrimitive -> d.asString
            d.isJsonArray -> d.asJsonArray.joinToString("；") { it.toString().trim('"') }
            else -> null
        }
    }

    private fun bizCodeOf(text: String): String? = jsonOf(text)
        ?.get("code")
        ?.takeIf { it.isJsonPrimitive }
        ?.asString
        ?.takeIf { it.isNotBlank() }

    private fun exec(r: Request): String {
        val res = try {
            client.newCall(r).execute()
        } catch (e: java.io.IOException) {
            throw ApiError(0, null, e)
        }
        res.use {
            val text = it.body?.string().orEmpty()
            if (!it.isSuccessful) throw ApiError(it.code, detailOf(text), null, bizCodeOf(text))
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

    /** 一页账单：服务端 full=1 拉回来的东西。total 是这次整库一共多少笔（翻页时每页都报同一个数）。 */
    data class TxnPage(val items: List<Txn>, val nextCursor: String?, val total: Int)

    /**
     * 整库拉一页回来（换手机、重装、清空本地后把服务器那份拉回来用）。
     * 软删的笔也会带 deleted=true 一起回来，调用方据此删本地行。
     */
    fun pullPage(cursor: String? = null, limit: Int = 500): TxnPage {
        val q = StringBuilder("/api/v1/txns?full=1&limit=$limit")
        if (!cursor.isNullOrBlank()) {
            q.append("&cursor=").append(java.net.URLEncoder.encode(cursor, "UTF-8"))
        }
        val o = gson.fromJson(exec(req(q.toString())), JsonObject::class.java)
        val arr = o.getAsJsonArray("items")
        val out = ArrayList<Txn>()
        if (arr != null) {
            for (el in arr) {
                runCatching { txnOf(el.asJsonObject) }.getOrNull()?.let { out.add(it) }
            }
        }
        return TxnPage(
            items = out,
            nextCursor = o.get("next_cursor")?.takeIf { !it.isJsonNull }?.asString?.takeIf { it.isNotBlank() },
            total = o.get("total")?.takeIf { !it.isJsonNull }?.asInt ?: out.size,
        )
    }

    /** 服务端那一条账单 → 本地 Txn。字段缺了就当没填，不崩。 */
    private fun txnOf(j: JsonObject): Txn {
        fun lng(k: String): Long? = j.get(k)?.takeIf { !it.isJsonNull }?.asLong?.takeIf { it > 0 }
        fun txt(k: String): String = j.get(k)?.takeIf { !it.isJsonNull }?.asString ?: ""
        val at = j.get("occurred_at")?.takeIf { !it.isJsonNull }?.asString
            ?.let {
                runCatching {
                    java.time.LocalDateTime.parse(it).atZone(java.time.ZoneId.systemDefault())
                        .toInstant().toEpochMilli()
                }.getOrNull()
            }
            ?: System.currentTimeMillis()
        return Txn(
            uuid = txt("client_uuid"),
            bookId = lng("book_id"),
            catId = lng("cat_id"),
            acctId = lng("account_id"),
            kind = txt("kind").ifBlank { "out" },
            cents = j.get("amount_cents")?.takeIf { !it.isJsonNull }?.asLong ?: 0L,
            at = at,
            note = txt("note"),
            source = txt("source").ifBlank { "manual" },
            // 服务端那份就是备份，拉回来即已同步，不用再推一遍（推上去反而可能覆盖别的设备改的）
            synced = true,
            deleted = j.get("deleted")?.takeIf { !it.isJsonNull }?.asBoolean ?: false,
        )
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
        // 服务端判断这句话是在问账（而不是要记一笔）时给 "query"，客户端据此转去问账接口
        val intent: String = "record",
    )

    fun parse(text: String): ParseResult {
        val body = gson.toJson(mapOf("text" to text))
        val o = gson.fromJson(exec(req("/api/v1/ai/parse", body, "POST")), JsonObject::class.java)
        fun lng(k: String): Long? = o.get(k)?.takeIf { !it.isJsonNull }?.asLong
        fun str(k: String): String? = o.get(k)?.takeIf { !it.isJsonNull }?.let { if (it is JsonPrimitive) it.asString else null }
        val at = o.get("occurred_at")?.takeIf { !it.isJsonNull }?.asString
            ?.let { runCatching { java.time.LocalDateTime.parse(it).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli() }.getOrNull() }
            ?: System.currentTimeMillis()
        val raw = o.get("raw")?.takeIf { !it.isJsonNull && it.isJsonObject }?.asJsonObject
        val suggest = o.get("suggest_category")?.takeIf { !it.isJsonNull && it.isJsonObject }?.asJsonObject
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
            needs = o.get("needs")?.takeIf { !it.isJsonNull && it.isJsonArray }?.let { a -> gson.fromJson(a, object : TypeToken<List<String>>() {}.type) } ?: emptyList(),
            engine = raw?.get("engine")?.takeIf { !it.isJsonNull }?.asString,
            suggestName = suggest?.get("name")?.takeIf { !it.isJsonNull }?.asString,
            suggestKind = suggest?.get("kind")?.takeIf { !it.isJsonNull }?.asString ?: "out",
            suggestIcon = suggest?.get("icon")?.takeIf { !it.isJsonNull }?.asString ?: "🏷",
            learnedRule = learned,
            intent = raw?.get("intent")?.takeIf { !it.isJsonNull }?.asString ?: "record",
        )
    }

    fun summary(month: String): JsonObject =
        gson.fromJson(exec(req("/api/v1/summary?month=$month")), JsonObject::class.java)

    /** 「它查了什么」里的一行：某个分类/账本/某天花了多少。 */
    data class AskRow(val name: String, val cents: Long, val count: Int)

    /**
     * 问账的结果。answer 是服务端写好的一句人话；plan 是校验后真正执行的条件（折叠展示用）；
     * totalCents/count/rows 是服务端用 SQL 算出来的真实数字，界面不自己算。
     */
    data class AskResult(
        val answer: String,
        val metric: String,
        val dateFrom: String,
        val dateTo: String,
        val categories: List<String>,
        val totalCents: Long,
        val count: Int,
        val rows: List<AskRow>,
    ) {
        /** 给用户看的「它查了什么」，例如「2026-11-01 ~ 2026-11-30 · 餐饮 · 合计」。 */
        val planText: String
            get() {
                val span = if (dateFrom.isNotEmpty()) "$dateFrom ~ $dateTo" else "全部时间"
                val what = if (categories.isEmpty()) "全部支出" else categories.joinToString("、")
                val metricCn = when (metric) {
                    "count" -> "笔数"
                    "avg" -> "平均"
                    else -> "合计"
                }
                return "$span · $what · $metricCn"
            }
    }

    /** 问一句账目统计。服务端的模型只做翻译，数字由服务端算，客户端不参与计算。 */
    fun ask(text: String): AskResult {
        val body = gson.toJson(mapOf("text" to text))
        val o = gson.fromJson(exec(req("/api/v1/ask", body, "POST")), JsonObject::class.java)
        val q = o.getAsJsonObject("query") ?: JsonObject()
        val d = o.getAsJsonObject("data") ?: JsonObject()
        val cats = q.getAsJsonArray("categories")
            ?.mapNotNull { runCatching { it.asString }.getOrNull() } ?: emptyList()
        val rows = d.getAsJsonArray("rows")?.mapNotNull { el ->
            runCatching {
                val r = el.asJsonObject
                AskRow(
                    name = r.get("name")?.takeIf { !it.isJsonNull }?.asString ?: "",
                    cents = r.get("cents")?.takeIf { !it.isJsonNull }?.asLong ?: 0L,
                    count = r.get("count")?.takeIf { !it.isJsonNull }?.asInt ?: 0,
                )
            }.getOrNull()
        } ?: emptyList()
        return AskResult(
            answer = o.get("answer")?.takeIf { !it.isJsonNull }?.asString ?: "",
            metric = q.get("metric")?.takeIf { !it.isJsonNull }?.asString ?: "sum",
            dateFrom = q.get("date_from")?.takeIf { !it.isJsonNull }?.asString ?: "",
            dateTo = q.get("date_to")?.takeIf { !it.isJsonNull }?.asString ?: "",
            categories = cats,
            totalCents = d.get("total_cents")?.takeIf { !it.isJsonNull }?.asLong ?: 0L,
            count = d.get("count")?.takeIf { !it.isJsonNull }?.asInt ?: 0,
            rows = rows,
        )
    }

    fun health(): Boolean = runCatching { exec(req("/health", auth = false)); true }.getOrDefault(false)
}
