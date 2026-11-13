package com.miaoledger.ui

import android.content.Context
import android.content.Intent
import android.speech.RecognizerIntent
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.awaitLongPressOrCancellation
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PieChart
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.data.Acct
import com.miaoledger.data.Api
import com.miaoledger.data.ApiError
import com.miaoledger.data.Backup
import com.miaoledger.data.Book
import com.miaoledger.data.Cat
import com.miaoledger.data.CsvExport
import com.miaoledger.data.Feedback
import com.miaoledger.data.LocalDb
import com.miaoledger.data.Prefs
import com.miaoledger.data.Sync
import com.miaoledger.data.Txn
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.roundToLong
import kotlinx.coroutines.withTimeoutOrNull

// ================================================================== 工具
private val moneyFmt = java.text.DecimalFormat("#,##0.00")
private val WEEK_CN = listOf("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

fun fmt(cents: Long): String = "¥" + moneyFmt.format(cents / 100.0)
fun fmtPlain(cents: Long): String = moneyFmt.format(cents / 100.0)

private fun dayOf(ms: Long): LocalDate = Instant.ofEpochMilli(ms).atZone(ZoneId.systemDefault()).toLocalDate()
private fun weekdayCn(d: LocalDate): String = WEEK_CN[d.dayOfWeek.value - 1]
private fun hhmm(ms: Long): String =
    LocalDateTime.ofInstant(Instant.ofEpochMilli(ms), ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("HH:mm"))

private fun toast(ctx: Context, msg: String) {
    // 录音/上传都在后台线程，Toast 必须在有 Looper 的线程弹
    android.os.Handler(android.os.Looper.getMainLooper()).post {
        runCatching { Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show() }
    }
}
private fun maskMoney(v: String, hidden: Boolean) = if (hidden) "••••" else v

internal fun parseCents(s: String): Long = ((s.toDoubleOrNull() ?: 0.0) * 100).roundToLong()

// 服务端分类默认图标都是 🏷，这里按名字补一套，保证一眼能认出分类
private val CAT_EMOJI = mapOf(
    "餐饮" to "🍜", "交通" to "🚌", "汽车" to "⚡", "购物" to "🛒", "烟酒" to "🚬",
    "育儿" to "🧸", "赡养" to "👴", "医疗" to "💊", "居家" to "🏠", "旅行" to "✈",
    "人情" to "🎁", "工资" to "💼", "娱乐" to "🎮", "学习" to "📚", "通讯" to "📱",
    "服饰" to "👕", "美容" to "💄", "宠物" to "🐾", "装修" to "🔨", "水电" to "💡",
    "红包" to "🧧", "转账" to "🔁", "其它" to "📌", "其他" to "📌",
)

internal fun catIcon(c: Cat?): String {
    if (c == null) return "📌"
    val raw = c.icon
    val byName = CAT_EMOJI.entries.firstOrNull { c.name.contains(it.key) }?.value
    return if (raw.isBlank() || raw == "🏷" || raw == "🏷️") byName ?: "📌" else raw
}

// ================================================================== 小零件
@Composable
fun AppCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Surface(color = MiaoCard, shape = RoundedCornerShape(18.dp), modifier = modifier.fillMaxWidth()) {
        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), content = content)
    }
}

@Composable
private fun Bubble(text: String, size: Int = 37, bg: Color = MiaoBlueSoft, font: Int = 17) {
    Box(Modifier.size(size.dp).background(bg, CircleShape), contentAlignment = Alignment.Center) {
        Text(text, fontSize = font.sp)
    }
}

@Composable
private fun SectionLabel(text: String) {
    Text(text, fontSize = 11.sp, color = MiaoDim, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
}

@Composable
private fun RoundArrow(glyph: String, size: Int = 36, font: Int = 17, onClick: () -> Unit) {
    Box(
        Modifier.size(size.dp).background(Color(0xBFFFFFFF), CircleShape).clickable { onClick() },
        contentAlignment = Alignment.Center,
    ) { Text(glyph, fontSize = font.sp, fontWeight = FontWeight.Bold, color = MiaoBlueDeep) }
}

@Composable
private fun MoneyText(cents: Long, kind: String, size: Int = 14, color: Color = MiaoInk) {
    Text(
        text = (if (kind == "in") "+" else "−") + fmt(cents),
        fontSize = size.sp,
        fontWeight = FontWeight.SemiBold,
        color = if (kind == "in") MiaoGreen else color,
    )
}

// ================================================================== 按住说话
/**
 * 按住说话手势：长按（或按下）开始录音，手指往上拖过阈值切「取消」态，松手回调结果。
 * 加号用 requireLongPress = true（短按进手动记账）；AI 页的「按住说话」条用 false（按下即录）。
 */
private fun Modifier.talkPress(
    requireLongPress: Boolean,
    cancelSlopPx: Float,
    onStart: () -> Unit,
    onCancelZone: (Boolean) -> Unit,
    onEnd: (cancelled: Boolean) -> Unit,
    onTap: () -> Unit = {},
): Modifier = pointerInput(requireLongPress, cancelSlopPx) {
    awaitEachGesture {
        val down = awaitFirstDown(requireUnconsumed = false)
        if (requireLongPress) {
            val lp = awaitLongPressOrCancellation(down.id)
            if (lp == null) {              // 手指先抬起来了 = 普通点击
                onTap()
                return@awaitEachGesture
            }
        }
        onStart()
        var cancelled = false
        while (true) {
            val ev = awaitPointerEvent()
            val ch = ev.changes.firstOrNull { it.id == down.id } ?: break
            val up = down.position.y - ch.position.y      // 往上拖为正
            val now = up > cancelSlopPx
            if (now != cancelled) {
                cancelled = now
                onCancelZone(cancelled)
            }
            ch.consume()
            if (!ch.pressed) break
        }
        onEnd(cancelled)
        onCancelZone(false)
    }
}

/** 录音浮层：绿色半透明渐变 + 小字实时提示；手指上滑进入取消态时整屏转红。 */
@Composable
private fun RecordingOverlay(heard: String, state: String, cancelZone: Boolean) {
    val bg = if (cancelZone) {
        Brush.verticalGradient(listOf(Color(0xD9DE4C48), Color(0xF0A8262B)))
    } else {
        Brush.verticalGradient(listOf(Color(0xC23BCB6A), Color(0xF0188E45)))
    }
    Box(Modifier.fillMaxSize().background(bg)) {
        Column(
            Modifier.align(Alignment.Center).padding(horizontal = 40.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                Modifier.size(62.dp).background(Color(0x33FFFFFF), CircleShape),
                contentAlignment = Alignment.Center,
            ) { Text(if (cancelZone) "✕" else "🎙", fontSize = 25.sp) }
            Spacer(Modifier.height(14.dp))
            Text(state, fontSize = 12.sp, color = Color(0xE6FFFFFF))
            Spacer(Modifier.height(8.dp))
            Text(
                heard.ifBlank { "松开手指，结束录音" },
                fontSize = 13.sp, color = Color.White, textAlign = TextAlign.Center, maxLines = 4,
            )
        }
        Box(
            Modifier.align(Alignment.BottomCenter).padding(bottom = 92.dp)
                .background(Color(0x33FFFFFF), RoundedCornerShape(20.dp))
                .padding(horizontal = 14.dp, vertical = 8.dp),
        ) {
            Text(
                if (cancelZone) "松开手指，取消录音" else "手指上滑，取消录音",
                fontSize = 12.sp, color = Color.White,
                fontWeight = if (cancelZone) FontWeight.Bold else FontWeight.Normal,
            )
        }
    }
}

// ================================================================== 底部导航
@Composable
fun MiaoBottomBar(
    tab: Int,
    onTab: (Int) -> Unit,
    onPlus: () -> Unit,
    onVoiceStart: () -> Unit,
    onVoiceCancelZone: (Boolean) -> Unit,
    onVoiceStop: (cancelled: Boolean) -> Unit,
) {
    val slop = with(LocalDensity.current) { 70.dp.toPx() }
    Column(Modifier.fillMaxWidth().background(Color.White)) {
        HorizontalDivider(color = MiaoLine, thickness = 1.dp)
        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().height(58.dp),
            verticalAlignment = Alignment.Top,
        ) {
            TabCell("明细", tab == 0, Modifier.weight(1f), Icons.Filled.Receipt) { onTab(0) }
            TabCell("统计", tab == 1, Modifier.weight(1f), Icons.Filled.PieChart) { onTab(1) }
            Box(Modifier.weight(1f), contentAlignment = Alignment.TopCenter) {
                Box(
                    Modifier.offset(y = (-16).dp).size(58.dp).background(MiaoBlue, CircleShape)
                        .talkPress(
                            requireLongPress = true,
                            cancelSlopPx = slop,
                            onStart = onVoiceStart,
                            onCancelZone = onVoiceCancelZone,
                            onEnd = { cancelled -> onVoiceStop(cancelled) },
                            onTap = onPlus,
                        ),
                    contentAlignment = Alignment.Center,
                ) { Icon(Icons.Filled.Add, null, tint = Color.White, modifier = Modifier.size(30.dp)) }
            }
            TabCell("AI", tab == 2, Modifier.weight(1f), Icons.Filled.AutoAwesome) { onTab(2) }
            TabCell("我的", tab == 3, Modifier.weight(1f), Icons.Filled.Person) { onTab(3) }
        }
    }
}

@Composable
private fun TabCell(
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
) {
    val tint = if (selected) MiaoInk else Color(0xFFB8BDC4)
    Column(
        modifier.height(58.dp).clickable { onClick() }.padding(top = 9.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, null, tint = tint, modifier = Modifier.size(21.dp))
        Spacer(Modifier.height(3.dp))
        Text(
            label, fontSize = 10.sp, color = tint,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
        )
    }
}

// ================================================================== 根
@Composable
fun AppRoot(prefs: Prefs, db: LocalDb, api: Api) {
    var loggedIn by remember { mutableStateOf(prefs.loggedIn) }
    var tab by remember { mutableIntStateOf(0) }
    var reload by remember { mutableIntStateOf(0) }
    val txns = remember(reload) { mutableStateListOf<Txn>().also { it.addAll(db.all()) } }
    var month by remember { mutableStateOf(YearMonth.now()) }
    var hidden by remember { mutableStateOf(false) }
    var statsTab by remember { mutableIntStateOf(0) }
    var statRange by remember { mutableIntStateOf(1) }
    var sheet by remember { mutableStateOf<String?>(null) }
    var aiSeed by remember { mutableStateOf("") }
    // 二级页只用这一个栈位：进哪一页、从哪个 tab 进来的，返回时按来源回去
    var sub by remember { mutableStateOf<String?>(null) }        // account / categories / memory / add
    var subFrom by remember { mutableIntStateOf(3) }             // 3 = 我的，2 = AI
    var bookId by remember { mutableStateOf(prefs.bookId) }
    var editTxn by remember { mutableStateOf<Txn?>(null) }
    var listening by remember { mutableStateOf(false) }
    var heard by remember { mutableStateOf("") }
    var hearState by remember { mutableStateOf("正在听…") }
    var cancelZone by remember { mutableStateOf(false) }
    // AI 页的对话记录挂在根上：切 tab / 进修改账单都不会丢
    val aiMsgs = remember { mutableStateListOf<AiMsg>() }
    val aiCards = remember { androidx.compose.runtime.mutableStateMapOf<String, Txn?>() }
    val ctx = LocalContext.current
    var micGranted by remember {
        mutableStateOf(
            androidx.core.content.ContextCompat.checkSelfPermission(ctx, android.Manifest.permission.RECORD_AUDIO) ==
                android.content.pm.PackageManager.PERMISSION_GRANTED
        )
    }

    fun refresh() { reload++ }

    // 一打开 App 就试着备份一次（没网就算了，不弹窗），并把「每 6 小时自动备份」排上
    androidx.compose.runtime.LaunchedEffect(Unit) {
        if (prefs.loggedIn) {
            Backup.ensurePeriodic(ctx)
            Backup.now(ctx)
        }
    }

    fun deleteTxn(t: Txn) {
        db.softDelete(t.uuid)
        Thread { runCatching { if (prefs.loggedIn) api.deleteTxn(t.uuid) } }
        refresh()
    }

    // 导出账单：弹出系统保存框，选好位置后在后台把 CSV 写进去
    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        Thread {
            val ok = runCatching {
                val csv = CsvExport.build(db.all(), prefs.cats, prefs.accts, prefs.books)
                val out = ctx.contentResolver.openOutputStream(uri) ?: error("打不开这个位置")
                out.use { it.write(csv.toByteArray(Charsets.UTF_8)) }
            }.isSuccess
            toast(ctx, if (ok) "导出好了，就在你选的地方" else "导出失败，换个位置再试")
        }.start()
    }

    fun doExport() {
        runCatching { exportLauncher.launch(CsvExport.defaultName()) }
            .onFailure { toast(ctx, "导出失败，换个位置再试") }
    }

    val asr = remember {
        CloudAsr(
            ctx, api,
            onState = { hearState = it },
            onFinal = { text ->
                listening = false
                heard = text
                if (text.isNotBlank()) {
                    aiSeed = text
                    tab = 2
                    sub = null
                    editTxn = null
                }
            },
            onError = { msg ->
                listening = false
                toast(ctx, msg)
            },
        )
    }
    androidx.compose.runtime.DisposableEffect(Unit) {
        onDispose { asr.destroy() }
    }

    val micPermLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        micGranted = ok
        if (ok) {
            heard = ""
            hearState = "正在听…"
            listening = true
            asr.start()
        } else {
            toast(ctx, "没给麦克风权限，先用文字输入")
        }
    }

    fun startListening() {
        if (!micGranted) {
            micPermLauncher.launch(android.Manifest.permission.RECORD_AUDIO)
            return
        }
        if (listening) return
        heard = ""
        hearState = "正在听…"
        cancelZone = false
        listening = true
        asr.start()
    }

    /** cancelled = 手指上滑松手，整段录音作废，不送识别。 */
    fun stopListening(cancelled: Boolean = false) {
        cancelZone = false
        if (!listening) return
        if (cancelled) {
            asr.cancel()
            listening = false
            return
        }
        hearState = "识别中…"
        asr.stop()
    }

    // 返回键按栈来，一级一级退：录音 → 浮层 → 二级页（回到它从哪儿进来的那个 tab）→
    // 别的 tab 回明细 → 已经在明细就放行（退到桌面）
    val atHomeRoot = tab == 0 && sub == null && sheet == null && !listening
    BackHandler(enabled = !atHomeRoot) {
        when {
            listening -> { asr.cancel(); listening = false; cancelZone = false }
            sheet != null -> sheet = null
            sub != null -> { sub = null; editTxn = null; tab = subFrom }
            else -> tab = 0
        }
    }

    if (!loggedIn) {
        AuthFlow(prefs, api) {
            loggedIn = true
            refresh()
            Backup.ensurePeriodic(ctx)
            Backup.now(ctx)
        }
        return
    }

    Box(Modifier.fillMaxSize().background(MiaoBg)) {
        Column(Modifier.fillMaxSize()) {
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when {
                    sub == "add" -> AddScreen(
                        prefs = prefs,
                        initial = editTxn,
                        onSave = { kind, cents, cat, acct, note, at ->
                            val old = editTxn
                            val newBookId = old?.bookId ?: prefs.bookId.takeIf { it > 0 }
                            db.upsertLocal(
                                Txn(
                                    uuid = old?.uuid ?: db.newUuid(),
                                    bookId = newBookId,
                                    catId = cat?.id,
                                    acctId = acct?.id,
                                    kind = kind,
                                    cents = cents,
                                    at = at,
                                    note = note,
                                    source = old?.source ?: "manual",
                                    synced = false,
                                    // AI 记的那笔要留着「它原先猜的是什么」，改完才能告诉它改成了啥
                                    parsedCatId = old?.parsedCatId,
                                    parsedAcctId = old?.parsedAcctId,
                                    parsedBookId = old?.parsedBookId,
                                    aiText = old?.aiText,
                                )
                            )
                            // 改过 AI 记的账单：把「原猜 → 改成」排队告诉服务器，它下次就能学
                            Feedback.correctionPayload(
                                old = old,
                                newCatId = cat?.id,
                                newAcctId = acct?.id,
                                newBookId = newBookId,
                                kind = kind,
                                cents = cents,
                                note = note,
                            )?.let { db.enqueueFeedback(it) }
                            prefs.lastAcctId = acct?.id ?: prefs.lastAcctId
                            Backup.afterSave(ctx)
                            sub = null
                            editTxn = null
                            refresh()
                        },
                        onDelete = { t -> deleteTxn(t); sub = null; editTxn = null },
                        onCancel = { sub = null; editTxn = null },
                    )
                    sub == "account" -> AccountScreen(
                        prefs = prefs, api = api, db = db,
                        onBack = { sub = null },
                        onWiped = { refresh() },
                        onLogout = {
                            // 退出前先把服务端那台设备的登录作废，再把本地登录状态清掉
                            Thread { runCatching { api.logout() } }.start()
                            prefs.token = ""
                            aiMsgs.clear()
                            aiCards.clear()
                            sub = null
                            tab = 0
                            loggedIn = false
                        },
                    )
                    sub == "categories" -> CategoryScreen(
                        prefs = prefs, api = api,
                        onBack = { sub = null },
                        onChanged = { refresh() },
                    )
                    sub == "memory" -> AiMemoryScreen(
                        prefs = prefs, api = api,
                        onBack = { sub = null },
                        onChanged = { refresh() },
                    )
                    tab == 0 -> HomeScreen(
                        prefs = prefs, txns = txns.toList(), bookId = bookId,
                        month = month, onMonth = { month = it },
                        hidden = hidden, onHidden = { hidden = it },
                        onBook = { sheet = "book" }, onSearch = { sheet = "search" },
                        onCalendar = { tab = 1; statsTab = 0 },
                        onEditTxn = { editTxn = it; subFrom = 0; sub = "add" },
                        onDeleteTxn = { deleteTxn(it) },
                    )
                    tab == 1 -> StatsScreen(
                        prefs = prefs, txns = txns.toList(), bookId = bookId,
                        month = month, onMonth = { month = it },
                        subTab = statsTab, onSubTab = { statsTab = it },
                        range = statRange, onRange = { statRange = it },
                        hidden = hidden,
                    )
                    tab == 2 -> AiScreen(
                        prefs = prefs, api = api, db = db,
                        msgs = aiMsgs, cardRows = aiCards,
                        seed = aiSeed, onSeedUsed = { aiSeed = "" },
                        onSaved = { refresh() },
                        micGranted = micGranted,
                        onAskMic = { micPermLauncher.launch(android.Manifest.permission.RECORD_AUDIO) },
                        onBack = { tab = 0 },
                        reloadVer = reload,
                        onEditTxn = { editTxn = it; subFrom = 2; sub = "add" },
                        onMemory = { subFrom = 2; sub = "memory" },
                    )
                    else -> MineScreen(
                        prefs = prefs, api = api, db = db,
                        onAccount = { subFrom = 3; sub = "account" },
                        onCategories = { subFrom = 3; sub = "categories" },
                        onExport = { doExport() },
                        onChanged = { refresh() },
                    )
                }
            }
            // AI 页不显示底部导航：那排按钮在 AI 页用不上，蓝色加号还会跟「按住说话」挤在一起
            if (sub == null && tab != 2) MiaoBottomBar(
                // 点底部任何一个 tab，都要把二级页收掉，否则画面不跟着变
                tab = tab, onTab = { tab = it; sub = null },
                onPlus = { editTxn = null; subFrom = tab; sub = "add" },
                onVoiceStart = { startListening() },
                onVoiceCancelZone = { cancelZone = it },
                onVoiceStop = { cancelled -> stopListening(cancelled) },
            )
        }

        SheetHost(sheet, onDismiss = { sheet = null }) {
            when (sheet) {
                "book" -> BookSheet(
                    prefs = prefs, txns = txns.toList(), api = api,
                    onPicked = { id -> prefs.bookId = id; bookId = id; sheet = null; refresh() },
                )
                "search" -> SearchSheet(
                    prefs = prefs, txns = txns.toList(), hidden = hidden,
                    onClose = { sheet = null },
                )
            }
        }

        if (listening) {
            // 兜底：12 秒还没结果就收摊，别让浮层卡住
            androidx.compose.runtime.LaunchedEffect(listening) {
                kotlinx.coroutines.delay(12_000)
                if (listening) {
                    asr.cancel()
                    listening = false
                    cancelZone = false
                    toast(ctx, "没听清，再说一次")
                }
            }
            RecordingOverlay(heard = heard, state = hearState, cancelZone = cancelZone)
        }
    }
}

@Composable
private fun SheetHost(which: String?, onDismiss: () -> Unit, content: @Composable () -> Unit) {
    if (which == null) return
    Box(Modifier.fillMaxSize()) {
        Box(
            Modifier.fillMaxSize().background(Color(0x47000000)).clickable { onDismiss() }
        )
        Surface(
            color = Color.White,
            shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth(),
        ) {
            Column(
                Modifier.navigationBarsPadding().padding(start = 18.dp, end = 18.dp, top = 8.dp, bottom = 20.dp)
            ) {
                Box(Modifier.fillMaxWidth().padding(bottom = 8.dp), contentAlignment = Alignment.Center) {
                    Box(Modifier.size(width = 34.dp, height = 4.dp).background(Color(0xFFE3E7EC), RoundedCornerShape(2.dp)))
                }
                content()
            }
        }
    }
}

@Composable
private fun SheetTitle(text: String) {
    Text(
        text, fontSize = 13.sp, color = MiaoDim, fontWeight = FontWeight.Normal,
        modifier = Modifier.fillMaxWidth().padding(bottom = 10.dp), textAlign = TextAlign.Center,
    )
}

// ================================================================== 明细
@Composable
fun HomeScreen(
    prefs: Prefs,
    txns: List<Txn>,
    bookId: Long,
    month: YearMonth,
    onMonth: (YearMonth) -> Unit,
    hidden: Boolean,
    onHidden: (Boolean) -> Unit,
    onBook: () -> Unit,
    onSearch: () -> Unit,
    onCalendar: () -> Unit,
    onEditTxn: (Txn) -> Unit,
    onDeleteTxn: (Txn) -> Unit,
) {
    var askDelete by remember { mutableStateOf<Txn?>(null) }
    val cats = prefs.cats.associateBy { it.id }
    val accts = prefs.accts.associateBy { it.id }
    val bookName = prefs.books.firstOrNull { it.id == bookId }?.name
        ?: prefs.books.firstOrNull()?.name ?: "日常账本"

    val inBook = txns.filter { bookId == 0L || it.bookId == null || it.bookId == bookId }
    val inMonth = inBook.filter { YearMonth.from(dayOf(it.at)) == month }
    val out = inMonth.filter { it.kind == "out" }.sumOf { it.cents }
    val income = inMonth.filter { it.kind == "in" }.sumOf { it.cents }
    val grouped = inMonth.groupBy { dayOf(it.at) }.toSortedMap(compareByDescending { it })

    Column(Modifier.fillMaxSize()) {
        Surface(color = MiaoBlue, shape = RoundedCornerShape(bottomStart = 20.dp, bottomEnd = 20.dp)) {
            Column(Modifier.statusBarsPadding().padding(start = 18.dp, end = 18.dp, top = 6.dp, bottom = 13.dp)) {
                Row(Modifier.fillMaxWidth().height(36.dp), verticalAlignment = Alignment.CenterVertically) {
                    Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
                        Row(
                            Modifier.clickable { onBook() }.padding(vertical = 6.dp, horizontal = 2.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(bookName, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF))
                            Spacer(Modifier.width(5.dp))
                            Text("▾", fontSize = 13.sp, color = Color(0xCCFFFFFF))
                        }
                    }
                    Box(Modifier.size(44.dp).clickable { onSearch() }, contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.Search, null, tint = Color(0xFFFFFFFF), modifier = Modifier.size(24.dp))
                    }
                    Spacer(Modifier.width(2.dp))
                    Box(Modifier.size(44.dp).clickable { onCalendar() }, contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.CalendarMonth, null, tint = Color(0xFFFFFFFF), modifier = Modifier.size(24.dp))
                    }
                }
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("本月支出", fontSize = 11.sp, color = Color(0xCCFFFFFF))
                            Spacer(Modifier.width(6.dp))
                            Icon(
                                if (hidden) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                null, tint = Color(0xCCFFFFFF),
                                modifier = Modifier.size(15.dp).clickable { onHidden(!hidden) },
                            )
                        }
                        Text(
                            maskMoney(fmt(out), hidden),
                            fontSize = 37.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF),
                            maxLines = 1, overflow = TextOverflow.Ellipsis,
                        )
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(1.dp).height(28.dp).background(Color(0x38FFFFFF)))
                        Spacer(Modifier.width(10.dp))
                        RoundArrow("‹", size = 32, font = 15) { onMonth(month.minusMonths(1)) }
                        Column(
                            Modifier.padding(horizontal = 8.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Text(
                                "${month.monthValue}月", fontSize = 28.sp, fontWeight = FontWeight.Bold,
                                color = Color(0xFFFFFFFF), maxLines = 1,
                            )
                            Text("${month.year}", fontSize = 14.sp, color = Color(0xB3FFFFFF), maxLines = 1)
                        }
                        RoundArrow("›", size = 32, font = 15) { onMonth(month.plusMonths(1)) }
                    }
                }
                Row(Modifier.fillMaxWidth().padding(top = 5.dp)) {
                    Text("收入 ", fontSize = 11.sp, color = Color(0xCCFFFFFF))
                    Text(maskMoney(fmt(income), hidden), fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFFFFFFFF))
                    Spacer(Modifier.width(18.dp))
                    Text("结余 ", fontSize = 11.sp, color = Color(0xCCFFFFFF))
                    Text(maskMoney(fmt(income - out), hidden), fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFFFFFFFF))
                }
            }
        }

        if (grouped.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(24.dp), contentAlignment = Alignment.TopCenter) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(top = 40.dp)) {
                    Text("🧾", fontSize = 40.sp)
                    Spacer(Modifier.height(10.dp))
                    Text("${month.monthValue}月还没记账", fontSize = 14.sp, color = MiaoInkSoft)
                    Spacer(Modifier.height(4.dp))
                    Text("点加号手动记账，长按加号语音记账", fontSize = 12.sp, color = MiaoDim)
                }
            }
        } else {
            LazyColumn(
                Modifier.fillMaxSize().padding(start = 14.dp, end = 14.dp, top = 10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                grouped.forEach { (day, rows) ->
                    item(key = "d$day") {
                        AppCard {
                            Row(
                                Modifier.fillMaxWidth().padding(horizontal = 2.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    "${day.monthValue}.${"%02d".format(day.dayOfMonth)} ${weekdayCn(day)}",
                                    fontSize = 11.sp, color = MiaoDim,
                                )
                                Spacer(Modifier.weight(1f))
                                val dOut = rows.filter { it.kind == "out" }.sumOf { it.cents }
                                Text("支出 ${fmtPlain(dOut)}", fontSize = 11.sp, color = MiaoDim)
                            }
                            rows.sortedByDescending { it.at }.forEachIndexed { i, t ->
                                if (i > 0) HorizontalDivider(color = MiaoLine)
                                TxnRow(
                                    t, cats[t.catId ?: -1L], accts[t.acctId ?: -1L], hidden,
                                    onClick = { onEditTxn(t) },
                                    onLongClick = { askDelete = t },
                                )
                            }
                        }
                    }
                }
                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }

    askDelete?.let { t ->
        val catName = cats[t.catId ?: -1L]?.name ?: "这笔"
        AlertDialog(
            onDismissRequest = { askDelete = null },
            title = { Text("删除这笔账？", fontSize = 15.sp) },
            text = { Text("$catName ${fmt(t.cents)}，删了就没了（可以再记一笔）。", fontSize = 13.sp) },
            confirmButton = {
                TextButton(onClick = { onDeleteTxn(t); askDelete = null }) {
                    Text("删除", color = MiaoRed, fontSize = 13.sp)
                }
            },
            dismissButton = { TextButton(onClick = { askDelete = null }) { Text("算了", fontSize = 13.sp) } },
        )
    }
}

@Composable
private fun TxnRow(
    t: Txn, cat: Cat?, acct: Acct?, hidden: Boolean,
    onClick: (() -> Unit)? = null,
    onLongClick: (() -> Unit)? = null,
) {
    Row(
        Modifier.fillMaxWidth()
            .then(
                if (onClick != null || onLongClick != null) Modifier.pointerInput(t.uuid) {
                    detectTapGestures(
                        onTap = { onClick?.invoke() },
                        onLongPress = { onLongClick?.invoke() },
                    )
                } else Modifier
            )
            .padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Bubble(catIcon(cat))
        Spacer(Modifier.width(11.dp))
        Column(Modifier.weight(1f)) {
            Text(cat?.name ?: "其它", fontSize = 14.sp, color = MiaoInk, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sub = listOfNotNull(t.note.takeIf { it.isNotBlank() }, acct?.name).joinToString(" · ")
            if (sub.isNotEmpty()) {
                Spacer(Modifier.height(2.dp))
                Text(sub, fontSize = 11.sp, color = MiaoDim, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.width(8.dp))
        if (hidden) Text("••••", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
        else MoneyText(t.cents, t.kind)
    }
}

// ================================================================== 记一笔
@Composable
fun AddScreen(
    prefs: Prefs,
    initial: Txn? = null,
    onSave: (String, Long, Cat?, Acct?, String, Long) -> Unit,
    onDelete: (Txn) -> Unit,
    onCancel: () -> Unit,
) {
    val ctx = LocalContext.current
    var kind by remember { mutableStateOf(initial?.kind ?: "out") }
    var expr by remember { mutableStateOf(initial?.let { fmtPlain(it.cents) } ?: "0") }
    var note by remember { mutableStateOf(initial?.note ?: "") }
    var cat by remember {
        mutableStateOf(
            prefs.cats.firstOrNull { it.id == initial?.catId }
                ?: prefs.cats.firstOrNull { it.name == "餐饮" }
                ?: prefs.cats.firstOrNull()
        )
    }
    var acct by remember {
        mutableStateOf(
            prefs.accts.firstOrNull { it.id == initial?.acctId }
                ?: prefs.accts.firstOrNull { it.id == prefs.lastAcctId }
                ?: prefs.accts.firstOrNull()
        )
    }
    var at by remember { mutableLongStateOf(initial?.at ?: System.currentTimeMillis()) }
    var askAcct by remember { mutableStateOf(false) }
    var askNote by remember { mutableStateOf(false) }
    var askDel by remember { mutableStateOf(false) }

    val cats = prefs.cats.filter { it.kind == kind }.ifEmpty { prefs.cats }
    val total = evalExpr(expr)
    val atDay = dayOf(at)
    val isToday = atDay == LocalDate.now()
    val dateLabel = if (isToday) "今天" else "${atDay.monthValue}.${"%02d".format(atDay.dayOfMonth)}"

    Column(Modifier.fillMaxSize().background(MiaoBg).statusBarsPadding().navigationBarsPadding()) {
        Surface(color = MiaoBlue, shape = RoundedCornerShape(bottomStart = 18.dp, bottomEnd = 18.dp)) {
            Column(Modifier.fillMaxWidth().padding(start = 4.dp, end = 12.dp, top = 2.dp, bottom = 10.dp)) {
                Row(Modifier.fillMaxWidth().height(46.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(46.dp).clickable { onCancel() }, contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.ArrowBackIosNew, null, tint = Color.White, modifier = Modifier.size(20.dp))
                    }
                    Text(
                        if (initial == null) "手动记账" else "修改账单",
                        fontSize = 17.sp, fontWeight = FontWeight.Bold, color = Color.White,
                    )
                    Spacer(Modifier.weight(1f))
                    if (initial != null) {
                        Text(
                            "删除", fontSize = 13.sp, color = Color(0xFFFFE3DE),
                            modifier = Modifier.clickable { askDel = true }.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
                Row(
                    Modifier.padding(horizontal = 10.dp).fillMaxWidth()
                        .background(Color(0x22FFFFFF), RoundedCornerShape(20.dp)).padding(3.dp)
                ) {
                    listOf("out" to "支出", "in" to "收入").forEach { (k, label) ->
                        val on = kind == k
                        Box(
                            Modifier.weight(1f).background(if (on) Color.White else Color.Transparent, RoundedCornerShape(17.dp))
                                .clickable { kind = k; cat = prefs.cats.firstOrNull { it.kind == k } ?: cat }
                                .padding(vertical = 8.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                label, fontSize = 14.sp,
                                color = if (on) MiaoInk else Color(0xB3FFFFFF),
                                fontWeight = if (on) FontWeight.Bold else FontWeight.Normal,
                            )
                        }
                    }
                }
            }
        }

        // 备注 + 账户 + 金额：一行看全，金额给足字号
        Surface(
            color = Color.White, shape = RoundedCornerShape(16.dp),
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
        ) {
            Row(Modifier.padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(44.dp).background(MiaoBlueSoft, CircleShape).clickable { askAcct = true },
                    contentAlignment = Alignment.Center,
                ) { Text("💳", fontSize = 19.sp) }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (note.isBlank()) "点击输入备注" else note,
                        fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        color = if (note.isBlank()) Color(0xFFB6BBC2) else MiaoInk,
                        modifier = Modifier.fillMaxWidth().clickable { askNote = true },
                    )
                    Spacer(Modifier.height(3.dp))
                    Text(
                        "${acct?.name ?: "未选账户"} · $dateLabel",
                        fontSize = 11.sp, color = MiaoDim, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.clickable { askAcct = true },
                    )
                }
                Spacer(Modifier.width(8.dp))
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        "¥$expr", fontSize = 26.sp, fontWeight = FontWeight.Bold, color = MiaoInk,
                        maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                    if (expr.any { it == '+' || it == '−' }) {
                        Text("= ¥${fmtPlain((total * 100).roundToLong())}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = MiaoOrange)
                    }
                }
            }
        }

        // 分类：4 列大圆图标，图标比原来大一圈，装不下就滚
        Surface(
            color = Color.White, shape = RoundedCornerShape(16.dp),
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
        ) {
            if (cats.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("还没有分类，去「我的 → 分类配置」里加", fontSize = 12.sp, color = MiaoDim)
                }
            } else {
                LazyVerticalGrid(
                    columns = GridCells.Fixed(4),
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(horizontal = 6.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    items(cats.size) { i ->
                        val c = cats[i]
                        val on = c.id == cat?.id
                        Column(
                            Modifier.clip(RoundedCornerShape(12.dp)).clickable { cat = c }.padding(vertical = 4.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Box(
                                Modifier.size(48.dp)
                                    .background(if (on) MiaoBlue else Color(0xFFF4F5F7), CircleShape),
                                contentAlignment = Alignment.Center,
                            ) { Text(catIcon(c), fontSize = 22.sp) }
                            Spacer(Modifier.height(5.dp))
                            Text(
                                c.name, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                color = if (on) MiaoInk else Color(0xFF6B727B),
                                fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                            )
                        }
                    }
                }
            }
        }

        // 键盘：固定 4 行高度，不再撑满整屏（键面 46dp 更紧凑）
        Column(
            Modifier.fillMaxWidth().padding(start = 12.dp, end = 12.dp, top = 8.dp, bottom = 6.dp)
        ) {
            val rows4 = listOf(
                listOf("1", "2", "3", "⌫"),
                listOf("4", "5", "6", "+"),
                listOf("7", "8", "9", "−"),
                listOf(".", "0", "今天", "完成"),
            )
            rows4.forEachIndexed { ri, row ->
                Row(Modifier.fillMaxWidth().height(46.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    row.forEach { k ->
                        val isOk = k == "完成"
                        val isFn = k == "⌫" || k == "+" || k == "−" || k == "今天"
                        Box(
                            Modifier.weight(1f).fillMaxHeight()
                                .background(
                                    when {
                                        isOk -> MiaoBlue
                                        isFn -> MiaoSegBg
                                        else -> Color.White
                                    },
                                    RoundedCornerShape(12.dp),
                                )
                                .clickable {
                                    when (k) {
                                        "⌫" -> expr = if (expr.length <= 1) "0" else expr.dropLast(1).ifBlank { "0" }
                                        "+", "−" -> {
                                            val last = expr.lastOrNull()
                                            expr = when {
                                                last == '+' || last == '−' -> expr.dropLast(1) + k
                                                expr == "0" -> expr
                                                expr.length > 16 -> expr
                                                else -> expr + k
                                            }
                                        }
                                        "今天" -> pickDate(ctx, at) { at = it }
                                        "完成" -> {
                                            val cents = (evalExpr(expr) * 100).roundToLong()
                                            if (cents > 0) onSave(kind, cents, cat, acct, note, at)
                                            else toast(ctx, "先输金额")
                                        }
                                        "." -> {
                                            val seg = expr.split('+', '−').lastOrNull().orEmpty()
                                            if (!seg.contains('.')) expr = if (seg.isEmpty()) expr + "0." else expr + "."
                                        }
                                        else -> {
                                            expr = when {
                                                expr == "0" -> k
                                                expr.length > 16 -> expr
                                                else -> expr + k
                                            }
                                        }
                                    }
                                },
                            contentAlignment = Alignment.Center,
                        ) {
                            if (k == "今天") {
                                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                    Text("📅", fontSize = 14.sp)
                                    Text(dateLabel, fontSize = 9.sp, color = Color(0xFF5C636C))
                                }
                            } else {
                                Text(
                                    k,
                                    fontSize = if (isOk) 15.sp else if (isFn) 18.sp else 20.sp,
                                    fontWeight = if (isOk) FontWeight.Bold else FontWeight.Normal,
                                    color = if (isOk) Color.White else if (isFn) Color(0xFF5C636C) else MiaoInk,
                                )
                            }
                        }
                    }
                }
                if (ri < rows4.size - 1) Spacer(Modifier.height(6.dp))
            }
        }
    }

    if (askAcct) {
        AlertDialog(
            onDismissRequest = { askAcct = false },
            confirmButton = {},
            dismissButton = { TextButton(onClick = { askAcct = false }) { Text("取消") } },
            title = { Text("账户", fontSize = 15.sp) },
            text = {
                Column {
                    prefs.accts.forEach { a ->
                        Row(
                            Modifier.fillMaxWidth().clickable { acct = a; askAcct = false }.padding(vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(a.name, fontSize = 14.sp)
                            Spacer(Modifier.weight(1f))
                            if (a.id == acct?.id) Icon(Icons.Filled.Check, null, tint = MiaoGold, modifier = Modifier.size(18.dp))
                        }
                    }
                    if (prefs.accts.isEmpty()) Text("还没有账户，联网后会自动同步过来。", fontSize = 12.sp, color = MiaoDim)
                }
            },
        )
    }

    if (askNote) {
        var tmp by remember { mutableStateOf(note) }
        AlertDialog(
            onDismissRequest = { askNote = false },
            confirmButton = { TextButton(onClick = { note = tmp; askNote = false }) { Text("好") } },
            dismissButton = { TextButton(onClick = { askNote = false }) { Text("取消") } },
            title = { Text("备注", fontSize = 15.sp) },
            text = {
                OutlinedTextField(
                    tmp, { tmp = it }, singleLine = true,
                    placeholder = { Text("比如：中午吃饭 AA", fontSize = 13.sp) },
                )
            },
        )
    }

    if (askDel && initial != null) {
        AlertDialog(
            onDismissRequest = { askDel = false },
            title = { Text("删除这笔账？", fontSize = 15.sp) },
            text = { Text("删了就没了。", fontSize = 13.sp) },
            confirmButton = {
                TextButton(onClick = { askDel = false; onDelete(initial) }) {
                    Text("删除", color = MiaoRed, fontSize = 13.sp)
                }
            },
            dismissButton = { TextButton(onClick = { askDel = false }) { Text("算了", fontSize = 13.sp) } },
        )
    }
}

/** 只有加减：把 "12+8.5-3" 算成一个数。 */
internal fun evalExpr(s: String): Double {
    val t = s.replace('−', '-')
    if (t.isBlank()) return 0.0
    var sum = 0.0
    var cur = StringBuilder()
    var sign = 1.0
    for (ch in t) {
        when (ch) {
            '+', '-' -> {
                sum += sign * (cur.toString().toDoubleOrNull() ?: 0.0)
                sign = if (ch == '-') -1.0 else 1.0
                cur = StringBuilder()
            }
            else -> if (ch.isDigit() || ch == '.') cur.append(ch)
        }
    }
    sum += sign * (cur.toString().toDoubleOrNull() ?: 0.0)
    return sum
}

private fun pickDate(ctx: Context, currentMs: Long, onPick: (Long) -> Unit) {
    val d = dayOf(currentMs)
    val dlg = android.app.DatePickerDialog(
        ctx,
        { _, y, m, dd ->
            val c = java.util.Calendar.getInstance()
            c.timeInMillis = currentMs
            c.set(y, m, dd)
            onPick(c.timeInMillis)
        },
        d.year, d.monthValue - 1, d.dayOfMonth,
    )
    dlg.show()
}

@Composable
private fun AddRow(key: String, value: String, dim: Boolean, onClick: (() -> Unit)?) {
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable { onClick() } else it }.padding(vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(key, fontSize = 12.sp, color = MiaoDim, modifier = Modifier.width(46.dp))
        Text(
            value, fontSize = 13.sp, color = if (dim) Color(0xFFC3C8CE) else MiaoInk,
            maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
        )
        if (onClick != null) Text("›", fontSize = 14.sp, color = MiaoDim)
    }
}

// ================================================================== 统计
@Composable
fun StatsScreen(
    prefs: Prefs,
    txns: List<Txn>,
    bookId: Long,
    month: YearMonth,
    onMonth: (YearMonth) -> Unit,
    subTab: Int,
    onSubTab: (Int) -> Unit,
    range: Int,
    onRange: (Int) -> Unit,
    hidden: Boolean,
) {
    val cats = prefs.cats.associateBy { it.id }
    val inBook = txns.filter { bookId == 0L || it.bookId == null || it.bookId == bookId }
    val monthRows = inBook.filter { YearMonth.from(dayOf(it.at)) == month }
    val outRows = monthRows.filter { it.kind == "out" }

    val rangeRows = when (range) {
        0 -> inBook.filter { it.at >= System.currentTimeMillis() - 7L * 86400_000L }
        2 -> inBook.filter { dayOf(it.at).year == month.year }
        else -> monthRows
    }
    val rangeOut = rangeRows.filter { it.kind == "out" }
    val rangeIn = rangeRows.filter { it.kind == "in" }
    val total = rangeOut.sumOf { it.cents }

    val byCat = rangeOut.groupBy { it.catId }.mapValues { e -> e.value.sumOf { it.cents } }
        .entries.sortedByDescending { it.value }.take(6)
    val byDay = outRows.groupBy { dayOf(it.at).dayOfMonth }.mapValues { e -> e.value.sumOf { it.cents } }
    var pickedDay by remember(month) { mutableIntStateOf(byDay.keys.maxOrNull() ?: 1) }
    val maxDay = byDay.values.maxOrNull() ?: 1L

    val months = (5 downTo 0).map { month.minusMonths(it.toLong()) }
    val monthTotals = months.map { ym ->
        ym to inBook.filter { YearMonth.from(dayOf(it.at)) == ym && it.kind == "out" }.sumOf { it.cents }
    }

    Column(Modifier.fillMaxSize()) {
        Surface(color = MiaoBlue, shape = RoundedCornerShape(bottomStart = 20.dp, bottomEnd = 20.dp)) {
            Column(Modifier.statusBarsPadding().padding(start = 18.dp, end = 18.dp, top = 8.dp, bottom = 12.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Row(Modifier.weight(1f).background(Color(0x22FFFFFF), RoundedCornerShape(20.dp)).padding(3.dp)) {
                        listOf("周", "月", "年").forEachIndexed { i, label ->
                            val on = range == i
                            Box(
                                Modifier.weight(1f).background(if (on) Color.White else Color.Transparent, RoundedCornerShape(16.dp))
                                    .clickable { onRange(i) }.padding(vertical = 6.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(label, fontSize = 12.sp, color = if (on) MiaoInk else Color(0xB3FFFFFF), fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
                            }
                        }
                    }
                    Spacer(Modifier.width(10.dp))
                    Text(
                        "支出 ▾", fontSize = 11.sp, color = Color(0xFFFFFFFF),
                        modifier = Modifier.background(Color(0x22FFFFFF), RoundedCornerShape(12.dp))
                            .padding(horizontal = 9.dp, vertical = 5.dp),
                    )
                }
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.Bottom) {
                    Column(Modifier.weight(1f)) {
                        Text(if (range == 1) "本月总支出" else if (range == 0) "近 7 天支出" else "今年总支出", fontSize = 11.sp, color = Color(0xCCFFFFFF))
                        Text(maskMoney(fmt(total), hidden), fontSize = 30.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF))
                        Text(
                            "总结余 " + maskMoney(fmt(rangeIn.sumOf { it.cents } - total), hidden),
                            fontSize = 11.sp, color = Color(0xCCFFFFFF), modifier = Modifier.padding(top = 2.dp),
                        )
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(1.dp).height(28.dp).background(Color(0x38FFFFFF)))
                        Spacer(Modifier.width(10.dp))
                        RoundArrow("‹") { onMonth(month.minusMonths(1)) }
                        Column(Modifier.padding(horizontal = 10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("${month.monthValue}月", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF))
                            Text("${month.year}", fontSize = 11.sp, color = Color(0xB3FFFFFF))
                        }
                        RoundArrow("›") { onMonth(month.plusMonths(1)) }
                    }
                }
            }
        }

        Row(
            Modifier.padding(start = 14.dp, end = 14.dp, top = 10.dp).fillMaxWidth()
                .background(MiaoSegBg, RoundedCornerShape(22.dp)).padding(3.dp)
        ) {
            listOf("日历", "图表").forEachIndexed { i, label ->
                val on = subTab == i
                Box(
                    Modifier.weight(1f).background(if (on) Color.White else Color.Transparent, RoundedCornerShape(18.dp))
                        .clickable { onSubTab(i) }.padding(vertical = 7.dp),
                    contentAlignment = Alignment.Center,
                ) { Text(label, fontSize = 12.sp, color = if (on) MiaoInk else Color(0xFF7B828B), fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal) }
            }
        }

        LazyColumn(
            Modifier.fillMaxSize().padding(start = 14.dp, end = 14.dp, top = 10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (subTab == 0) {
                item {
                    AppCard {
                        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("${month.monthValue}月支出日历", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
                            Spacer(Modifier.weight(1f))
                            Text("颜色越深花得越多", fontSize = 10.sp, color = MiaoDim)
                        }
                        Spacer(Modifier.height(6.dp))
                        Row(Modifier.fillMaxWidth()) {
                            listOf("一", "二", "三", "四", "五", "六", "日").forEach {
                                Text(it, fontSize = 10.sp, color = MiaoDim, textAlign = TextAlign.Center, modifier = Modifier.weight(1f))
                            }
                        }
                        Spacer(Modifier.height(4.dp))
                        CalendarGrid(month, byDay, maxDay, pickedDay) { pickedDay = it }
                    }
                }
                item {
                    val dayRows = outRows.filter { dayOf(it.at).dayOfMonth == pickedDay }
                    AppCard {
                        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("${month.monthValue}月${pickedDay}日", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
                            Spacer(Modifier.weight(1f))
                            Text("支出 ${fmtPlain(dayRows.sumOf { it.cents })} · ${dayRows.size} 笔", fontSize = 10.sp, color = MiaoDim)
                        }
                        if (dayRows.isEmpty()) {
                            Text("这天没花钱", fontSize = 12.sp, color = MiaoDim, modifier = Modifier.padding(vertical = 14.dp))
                        } else {
                            dayRows.sortedByDescending { it.at }.forEachIndexed { i, t ->
                                if (i > 0) HorizontalDivider(color = MiaoLine)
                                TxnRow(t, cats[t.catId ?: -1L], null, hidden)
                            }
                        }
                    }
                }
            } else {
                item { DonutCard(byCat, cats, total, month.monthValue) }
                item { RankCard(byCat, cats, total) }
                item { MonthBarsCard(monthTotals, month) }
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun CalendarGrid(month: YearMonth, byDay: Map<Int, Long>, maxDay: Long, picked: Int, onPick: (Int) -> Unit) {
    val first = month.atDay(1)
    val offset = first.dayOfWeek.value - 1          // 周一=0
    val len = month.lengthOfMonth()
    val cells = offset + len
    val rows = (cells + 6) / 7
    Column {
        for (r in 0 until rows) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                for (c in 0 until 7) {
                    val idx = r * 7 + c
                    val dayNum = idx - offset + 1
                    if (dayNum < 1 || dayNum > len) {
                        Spacer(Modifier.weight(1f).aspectRatio(0.88f))
                    } else {
                        val amt = byDay[dayNum] ?: 0L
                        val ratio = if (maxDay <= 0) 0f else amt.toFloat() / maxDay
                        val bg = when {
                            amt == 0L -> Color(0xFFFAFBFC)
                            ratio < 0.25f -> Color(0xFFFFFBE0)
                            ratio < 0.5f -> Color(0xFFFFF0AE)
                            ratio < 0.8f -> Color(0xFFFFD9A3)
                            else -> Color(0xFFFFB877)
                        }
                        Column(
                            Modifier.weight(1f).aspectRatio(0.88f)
                                .background(bg, RoundedCornerShape(8.dp))
                                .border(if (dayNum == picked) 1.5.dp else 0.dp, if (dayNum == picked) MiaoBlueLine else Color.Transparent, RoundedCornerShape(8.dp))
                                .clickable { onPick(dayNum) },
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.Center,
                        ) {
                            val today = LocalDate.now()
                            val isToday = month == YearMonth.from(today) && dayNum == today.dayOfMonth
                            Text(
                                "$dayNum", fontSize = 11.sp,
                                color = if (ratio >= 0.8f && amt > 0) Color(0xFF5A3200) else Color(0xFF5C636C),
                                fontWeight = if (isToday) FontWeight.Bold else FontWeight.Normal,
                            )
                            if (amt > 0) Text("${amt / 100}", fontSize = 7.sp, color = Color(0xFF8B8F95), maxLines = 1)
                            if (isToday) {
                                Box(Modifier.padding(top = 1.dp).size(3.dp).background(Color(0xFFE07B00), CircleShape))
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(4.dp))
        }
    }
}

private val PIE_COLORS = listOf(MiaoOrange, Color(0xFFFFD98A), MiaoPink, Color(0xFFCFE7FF), Color(0xFFB8E6C9), Color(0xFFE0D4FF))

@Composable
private fun DonutCard(byCat: List<Map.Entry<Long?, Long>>, cats: Map<Long, Cat>, total: Long, monthNum: Int) {
    AppCard {
        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("支出构成", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Text("${monthNum}月 ${fmt(total)}", fontSize = 10.sp, color = MiaoDim, maxLines = 1)
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(124.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.fillMaxSize()) {
                    val sw = 24.dp.toPx()
                    if (total <= 0L) {
                        drawArc(
                            color = MiaoTrack, startAngle = 0f, sweepAngle = 360f, useCenter = false,
                            topLeft = Offset(sw / 2, sw / 2),
                            size = Size(this.size.width - sw, this.size.height - sw),
                            style = Stroke(width = sw),
                        )
                    } else {
                        var start = -90f
                        byCat.forEachIndexed { i, e ->
                            val sweep = 360f * e.value.toFloat() / total.toFloat()
                            drawArc(
                                color = PIE_COLORS[i % PIE_COLORS.size], startAngle = start, sweepAngle = sweep, useCenter = false,
                                topLeft = Offset(sw / 2, sw / 2),
                                size = Size(this.size.width - sw, this.size.height - sw),
                                style = Stroke(width = sw),
                            )
                            start += sweep
                        }
                    }
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("合计", fontSize = 10.sp, color = MiaoDim)
                    Text("${total / 100}", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = MiaoInk)
                }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(7.dp)) {
                if (byCat.isEmpty()) Text("这个区间还没记账", fontSize = 12.sp, color = MiaoDim)
                byCat.forEachIndexed { i, e ->
                    val name = cats[e.key ?: -1L]?.name ?: "其它"
                    val pct = if (total > 0) e.value.toFloat() / total else 0f
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).background(PIE_COLORS[i % PIE_COLORS.size], CircleShape))
                        Spacer(Modifier.width(6.dp))
                        Text("$name ${(pct * 100).toInt()}%", fontSize = 11.sp, color = MiaoInkSoft, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Spacer(Modifier.weight(1f))
                        Text(fmt(e.value), fontSize = 11.sp, color = MiaoInkSoft, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

@Composable
private fun RankCard(byCat: List<Map.Entry<Long?, Long>>, cats: Map<Long, Cat>, total: Long) {
    AppCard {
        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("支出排行", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Text("前 ${byCat.size} 名", fontSize = 10.sp, color = MiaoDim)
        }
        Spacer(Modifier.height(6.dp))
        if (byCat.isEmpty()) Text("没数据", fontSize = 12.sp, color = MiaoDim, modifier = Modifier.padding(vertical = 10.dp))
        byCat.forEach { e ->
            val name = cats[e.key ?: -1L]?.name ?: "其它"
            val pct = if (total > 0) e.value.toFloat() / total else 0f
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Bubble(catIcon(cats[e.key ?: -1L]), size = 32, font = 14)
                Spacer(Modifier.width(9.dp))
                Column(Modifier.weight(1f)) {
                    Row {
                        Text(name, fontSize = 12.sp, color = MiaoInk)
                        Spacer(Modifier.weight(1f))
                        Text(fmt(e.value), fontSize = 12.sp, color = MiaoInkSoft, fontWeight = FontWeight.SemiBold)
                    }
                    Spacer(Modifier.height(4.dp))
                    Box(Modifier.fillMaxWidth().height(8.dp).background(MiaoTrack, RoundedCornerShape(6.dp))) {
                        Box(Modifier.fillMaxWidth(pct.coerceAtLeast(0.03f)).height(8.dp).background(MiaoOrange, RoundedCornerShape(6.dp)))
                    }
                }
            }
        }
    }
}

@Composable
private fun MonthBarsCard(monthTotals: List<Pair<YearMonth, Long>>, cur: YearMonth) {
    AppCard {
        Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("月度对比", fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            val hi = monthTotals.maxByOrNull { it.second }
            Text(if (hi != null && hi.second > 0) "${hi.first.monthValue}月最高" else "填几个月就有对比了", fontSize = 10.sp, color = MiaoDim)
        }
        Spacer(Modifier.height(14.dp))
        val maxV = (monthTotals.maxOfOrNull { it.second } ?: 0L).coerceAtLeast(1L)
        Row(Modifier.fillMaxWidth().height(96.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            monthTotals.forEach { (ym, cents) ->
                Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Bottom) {
                    Text(if (cents > 0) "${cents / 100}" else "", fontSize = 7.sp, color = MiaoDim, maxLines = 1)
                    Spacer(Modifier.height(2.dp))
                    val f = cents.toFloat() / maxV.toFloat()
                    Box(
                        Modifier.fillMaxWidth().height((78f * f).dp.coerceAtLeast(2.dp))
                            .background(if (ym == cur) MiaoOrange else Color(0xFFFFD9A3), RoundedCornerShape(topStart = 6.dp, topEnd = 6.dp))
                    )
                }
            }
        }
        Spacer(Modifier.height(6.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            monthTotals.forEach { (ym, _) ->
                Text("${ym.monthValue}月", fontSize = 8.sp, color = MiaoDim, textAlign = TextAlign.Center, modifier = Modifier.weight(1f), maxLines = 1)
            }
        }
    }
}

// ================================================================== AI
sealed interface AiMsg {
    data class Mine(val text: String) : AiMsg
    data class Bot(val text: String) : AiMsg
    data class Card(val uuid: String) : AiMsg
}

@Composable
fun AiScreen(
    prefs: Prefs,
    api: Api,
    db: LocalDb,
    msgs: MutableList<AiMsg>,
    cardRows: MutableMap<String, Txn?>,
    seed: String,
    onSeedUsed: () -> Unit,
    onSaved: () -> Unit,
    micGranted: Boolean,
    onAskMic: () -> Unit,
    onBack: () -> Unit,
    reloadVer: Int,
    onEditTxn: (Txn) -> Unit,
    onMemory: () -> Unit,
) {
    val ctx = LocalContext.current
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var askDelete by remember { mutableStateOf<String?>(null) }
    val cats = prefs.cats.associateBy { it.id }
    var voiceMode by remember { mutableStateOf(true) }
    var aiListen by remember { mutableStateOf(false) }
    var aiCancel by remember { mutableStateOf(false) }
    var partial by remember { mutableStateOf("") }
    var pendingVoice by remember { mutableStateOf("") }
    // AI 建议新建分类时挂在这儿：uuid 到 那次解析结果
    var suggest by remember { mutableStateOf<Pair<String, Api.ParseResult>?>(null) }
    var creatingCat by remember { mutableStateOf(false) }

    // 从别处（改账单页 / 明细页）动过数据后，把卡片上的内容重新读一遍
    androidx.compose.runtime.LaunchedEffect(reloadVer) {
        msgs.filterIsInstance<AiMsg.Card>().forEach { c -> cardRows[c.uuid] = db.byUuid(c.uuid) }
    }
    val aiAsr = remember {
        CloudAsr(
            ctx, api,
            onState = { partial = it },
            onFinal = { t ->
                aiListen = false
                aiCancel = false
                partial = ""
                pendingVoice = t
            },
            onError = { m ->
                aiListen = false
                aiCancel = false
                partial = ""
                toast(ctx, m)
            },
        )
    }
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { aiAsr.destroy() } }

    fun localAnswer(q: String, txns: List<Txn>): String {
        val thisMonth = YearMonth.now()
        val rows = txns.filter { YearMonth.from(dayOf(it.at)) == thisMonth && it.kind == "out" }
        val lastRows = txns.filter { YearMonth.from(dayOf(it.at)) == thisMonth.minusMonths(1) && it.kind == "out" }
        val total = rows.sumOf { it.cents }
        val last = lastRows.sumOf { it.cents }
        if (rows.isEmpty()) return "这个月还一笔没记呢，先记两笔我才有话说。"
        val byCat = rows.groupBy { it.catId }.mapValues { e -> e.value.sumOf { it.cents } }.entries.sortedByDescending { it.value }
        val top = byCat.take(3).joinToString("\n") { e ->
            val n = cats[e.key ?: -1L]?.name ?: "其它"
            "· $n ${fmt(e.value)}（${(e.value * 100 / total)}%）"
        }
        val trend = when {
            last <= 0L -> "上月没有可比数据。"
            total > last -> "比上月多 ${fmt(total - last)}。"
            else -> "比上月少 ${fmt(last - total)}。"
        }
        val extra = when {
            q.contains("省") -> "\n想省：先看排第一那类，把它砍三成，一个月就能省 ${fmt(byCat.first().value * 3 / 10)}。"
            q.contains("育儿") || q.contains("孩子") -> byCat.firstOrNull { cats[it.key ?: -1L]?.name?.contains("育儿") == true }
                ?.let { "\n育儿这个月花了 ${fmt(it.value)}。" } ?: "\n这个月育儿还没花钱。"
            else -> ""
        }
        return "本月支出 ${fmt(total)}，$trend\n花得最多的是：\n$top$extra"
    }

    fun looksLikeTxn(s: String): Boolean {
        val q = s.contains("？") || s.contains("?")
        val kw = listOf("多少", "为什么", "哪", "省", "比上", "排行", "分析", "怎么样", "花哪")
        return !q && kw.none { s.contains(it) }
    }

    fun mainPost(block: () -> Unit) {
        android.os.Handler(android.os.Looper.getMainLooper()).post { block() }
    }

    /** 解析出来就直接入账（不再让用户点「确认入账」）。AI 原先猜的分类也存着，改的时候才知道它猜的啥。 */
    fun saveParsed(r: Api.ParseResult, text: String) {
        val cents = r.cents
        if (cents == null) {
            mainPost {
                msgs.add(AiMsg.Bot("没听出金额，再说一次？比如「买菜 35，记在日常账本」"))
                busy = false
            }
            return
        }
        val bookId = r.bookId ?: prefs.bookId.takeIf { it > 0 }
        val acctId = r.acctId ?: prefs.lastAcctId.takeIf { it > 0 }
        val uuid = db.newUuid()
        db.upsertLocal(
            Txn(
                uuid = uuid,
                bookId = bookId,
                catId = r.catId,
                acctId = acctId,
                kind = r.kind,
                cents = cents,
                at = r.at,
                note = r.note,
                source = "ai",
                parsedCatId = r.catId,
                parsedAcctId = acctId,
                parsedBookId = bookId,
                aiText = text,
            )
        )
        mainPost {
            cardRows[uuid] = db.byUuid(uuid)
            msgs.add(AiMsg.Card(uuid))
            if (!r.learnedRule.isNullOrBlank()) {
                prefs.lastLearnAt = System.currentTimeMillis()
                prefs.lastLearned = r.learnedRule
                msgs.add(AiMsg.Bot("AI 已学会：${r.learnedRule}"))
            }
            // AI 觉得这笔该进一个还不存在的分类：先入账，再问一句要不要建
            if (!r.suggestName.isNullOrBlank() && r.catId == null) suggest = uuid to r
            busy = false
            onSaved()
        }
    }

    /** 用户同意建分类：在服务器上建一个，再把这笔改挂过去；建不出来也不拦着记账。 */
    fun acceptSuggest(uuid: String, r: Api.ParseResult) {
        val name = r.suggestName?.trim().orEmpty()
        if (name.isEmpty()) { suggest = null; return }
        creatingCat = true
        Thread {
            try {
                val id = api.createCategory(name, r.suggestKind, r.suggestIcon)
                api.syncMeta()
                db.byUuid(uuid)?.let { old ->
                    db.upsertLocal(old.copy(catId = id, synced = false))
                    // 采纳了「新建分类」建议：告诉服务端这个名字，下次它直接归对
                    Feedback.correctionPayload(
                        old = old,
                        newCatId = id,
                        newAcctId = old.parsedAcctId ?: old.acctId,
                        newBookId = old.parsedBookId ?: old.bookId,
                        kind = old.kind,
                        cents = old.cents,
                        note = old.note,
                        newCategory = Feedback.newCategory(name, r.suggestKind, r.suggestIcon),
                    )?.let { db.enqueueFeedback(it) }
                }
                mainPost {
                    cardRows[uuid] = db.byUuid(uuid)
                    msgs.add(AiMsg.Bot("新建了分类「$name」，以后这类就自动归它。"))
                    creatingCat = false
                    suggest = null
                    onSaved()
                }
            } catch (e: Exception) {
                mainPost {
                    msgs.add(AiMsg.Bot((e as? ApiError)?.message ?: "分类没建成，等联网了再说；这笔先记着。"))
                    creatingCat = false
                    suggest = null
                }
            }
        }.start()
    }

    fun deleteCard(uuid: String) {
        db.softDelete(uuid)
        Thread { runCatching { if (prefs.loggedIn) api.deleteTxn(uuid) } }
        cardRows[uuid] = db.byUuid(uuid)      // 这行已 deleted=1，卡片会显示「已删除」
        onSaved()
    }

    fun send(text: String) {
        val t = text.trim()
        if (t.isEmpty()) return
        msgs.add(AiMsg.Mine(t))
        input = ""
        if (looksLikeTxn(t)) {
            busy = true
            Thread {
                try {
                    saveParsed(api.parse(t), t)
                } catch (e: Exception) {
                    mainPost {
                        msgs.add(
                            AiMsg.Bot(
                                ((e as? ApiError)?.message ?: "连不上服务器。")
                                    + " 没网也能先手打记一笔，回头会自动补上。"
                            )
                        )
                        busy = false
                    }
                }
            }.start()
        } else {
            busy = true
            Thread {
                val answer = localAnswer(t, db.all())
                mainPost {
                    msgs.add(AiMsg.Bot(answer))
                    busy = false
                }
            }.start()
        }
    }

    androidx.compose.runtime.LaunchedEffect(seed) {
        if (seed.isNotBlank()) {
            send(seed)
            onSeedUsed()
        }
    }

    androidx.compose.runtime.LaunchedEffect(pendingVoice) {
        if (pendingVoice.isNotBlank()) {
            val t = pendingVoice
            pendingVoice = ""
            send(t)
        }
    }

    // imePadding：软键盘弹起来时整页往上顶，输入栏不被键盘压住
    Box(Modifier.fillMaxSize().background(MiaoBg).imePadding()) {
    Column(Modifier.fillMaxSize()) {
        Row(
            Modifier.fillMaxWidth().statusBarsPadding()
                .background(androidx.compose.ui.graphics.Brush.linearGradient(listOf(Color(0xFFEAF4FD), Color(0xFFF1F8FE))))
                .padding(start = 8.dp, end = 18.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(34.dp).clickable { onBack() }, contentAlignment = Alignment.Center) {
                Text("‹", fontSize = 26.sp, color = MiaoInk)
            }
            Spacer(Modifier.width(4.dp))
            Box(Modifier.size(38.dp).background(Color.White, CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.AutoAwesome, null, tint = MiaoGold, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("记账助手", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
                Text("可以问账目，也可以直接说出账目", fontSize = 10.sp, color = Color(0xFF8A8F96))
            }
            // 右上角进「它的记忆」：AI 自己学的规矩都在那儿，只读，想删可以删
            Box(
                Modifier.background(Color.White, RoundedCornerShape(14.dp)).clickable { onMemory() }
                    .padding(horizontal = 11.dp, vertical = 9.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text("它的记忆", fontSize = 11.sp, color = MiaoInkSoft)
            }
        }

        Column(Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("这个月哪花超了？", "和上月比", "育儿花了多少", "帮我省点钱").chunked(2).forEach { pair ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    pair.forEach { q -> PromptChip(q) { send(q) } }
                }
            }
        }

        LazyColumn(
            Modifier.weight(1f).fillMaxWidth().padding(horizontal = 18.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(top = 10.dp, bottom = 10.dp),
        ) {
            if (msgs.isEmpty()) {
                item {
                    Row(verticalAlignment = Alignment.Top) {
                        Box(Modifier.size(28.dp).background(Color.White, CircleShape), contentAlignment = Alignment.Center) {
                            Icon(Icons.Filled.AutoAwesome, null, tint = MiaoGold, modifier = Modifier.size(15.dp))
                        }
                        Spacer(Modifier.width(8.dp))
                        Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth(0.92f)) {
                            Column(Modifier.padding(horizontal = 13.dp, vertical = 11.dp)) {
                                Text("我是记账助手。你可以直接说出账目，也可以问账上的事。", fontSize = 13.sp, color = MiaoInk)
                                Spacer(Modifier.height(6.dp))
                                Text("例如：「买马桶 2100，记在赡养老人账本上」", fontSize = 11.sp, color = MiaoDim)
                            }
                        }
                    }
                }
            }
            items(msgs.size) { i ->
                when (val m = msgs[i]) {
                    is AiMsg.Mine -> Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.End,
                    ) {
                        Surface(
                            color = MiaoBlueSoft, shape = RoundedCornerShape(16.dp),
                            modifier = Modifier.widthIn(max = 290.dp),
                        ) {
                            Text(m.text, fontSize = 13.sp, color = MiaoInk, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                    is AiMsg.Bot -> Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) {
                        Box(
                            Modifier.size(28.dp).background(Color.White, CircleShape),
                            contentAlignment = Alignment.Center,
                        ) { Icon(Icons.Filled.AutoAwesome, null, tint = MiaoGold, modifier = Modifier.size(15.dp)) }
                        Spacer(Modifier.width(8.dp))
                        Surface(
                            color = Color.White, shape = RoundedCornerShape(16.dp),
                            modifier = Modifier.widthIn(max = 290.dp),
                        ) {
                            Text(m.text, fontSize = 13.sp, color = MiaoInk, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                    is AiMsg.Card -> {
                        val t = cardRows[m.uuid]
                        if (t != null) {
                            AiTxnCard(
                                t = t, cat = cats[t.catId ?: -1L], deleted = t.deleted,
                                onEdit = { onEditTxn(t) },
                                onDelete = { askDelete = m.uuid },
                            )
                        }
                    }
                }
            }
            if (busy) {
                item { Text("在算…", fontSize = 11.sp, color = MiaoDim, modifier = Modifier.padding(vertical = 4.dp)) }
            }
        }

        Row(
            Modifier.fillMaxWidth().navigationBarsPadding().padding(start = 18.dp, end = 18.dp, bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(
                color = Color.White, shape = RoundedCornerShape(24.dp), shadowElevation = 8.dp,
                modifier = Modifier.weight(1f),
            ) {
                Row(
                    Modifier.fillMaxWidth().padding(start = 14.dp, end = 6.dp, top = 5.dp, bottom = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (voiceMode) {
                        val aiSlop = with(LocalDensity.current) { 70.dp.toPx() }
                        Box(
                            Modifier.weight(1f).talkPress(
                                requireLongPress = false,
                                cancelSlopPx = aiSlop,
                                onStart = {
                                    if (!micGranted) {
                                        onAskMic()
                                    } else {
                                        partial = ""
                                        aiCancel = false
                                        aiListen = true
                                        aiAsr.start()
                                    }
                                },
                                onCancelZone = { aiCancel = it },
                                onEnd = { cancelled ->
                                    if (cancelled) {
                                        aiAsr.cancel()
                                        aiListen = false
                                        aiCancel = false
                                        partial = ""
                                    } else if (aiListen) {
                                        aiAsr.stop()
                                    }
                                },
                            ).padding(vertical = 9.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                when {
                                    aiListen && partial.isNotBlank() -> partial
                                    aiListen -> "松开发送"
                                    else -> "按住说话"
                                },
                                fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                                color = if (aiListen) MiaoInk else MiaoInkSoft,
                            )
                        }
                    } else {
                        BasicTextField(
                            value = input, onValueChange = { input = it },
                            textStyle = TextStyle(fontSize = 13.sp, color = MiaoInk),
                            cursorBrush = SolidColor(MiaoGold),
                            modifier = Modifier.weight(1f),
                            decorationBox = { inner ->
                                Box {
                                    if (input.isEmpty()) Text("点击输入文字", fontSize = 13.sp, color = Color(0xFFB6BBC2))
                                    inner()
                                }
                            },
                        )
                        Spacer(Modifier.width(6.dp))
                        Box(
                            Modifier.size(34.dp).background(MiaoBlue, CircleShape).clickable { send(input) },
                            contentAlignment = Alignment.Center,
                        ) { Text("→", fontSize = 15.sp, color = Color(0xFFFFFFFF)) }
                    }
                }
            }
            Spacer(Modifier.width(8.dp))
            Box(
                Modifier.size(44.dp).background(Color.White, CircleShape).clickable { voiceMode = !voiceMode },
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (voiceMode) Icons.Filled.Keyboard else Icons.Filled.Mic,
                    null, tint = MiaoInkSoft, modifier = Modifier.size(22.dp),
                )
            }
        }
        }
        if (aiListen) RecordingOverlay(heard = partial, state = "正在听…", cancelZone = aiCancel)

        askDelete?.let { u ->
            AlertDialog(
                onDismissRequest = { askDelete = null },
                title = { Text("删除这笔账？", fontSize = 15.sp) },
                text = { Text(cardRows[u]?.let { "${cats[it.catId ?: -1L]?.name ?: "这笔"} ${fmt(it.cents)}，删了就没了。" } ?: "删了就没了。", fontSize = 13.sp) },
                confirmButton = {
                    TextButton(onClick = { deleteCard(u); askDelete = null }) {
                        Text("删除", color = MiaoRed, fontSize = 13.sp)
                    }
                },
                dismissButton = { TextButton(onClick = { askDelete = null }) { Text("算了", fontSize = 13.sp) } },
            )
        }

        // AI 猜到一个还不存在的分类：账已经记上了，这里只问一句要不要建
        suggest?.let { (uuid, r) ->
            val name = r.suggestName.orEmpty()
            AlertDialog(
                onDismissRequest = { if (!creatingCat) suggest = null },
                title = { Text("要新建一个分类吗？", fontSize = 15.sp) },
                text = {
                    Text(
                        "AI 觉得「$name」是它没见过的分类。建一个，以后这类钱就自动归进去。",
                        fontSize = 13.sp, lineHeight = 20.sp,
                    )
                },
                confirmButton = {
                    TextButton(onClick = { acceptSuggest(uuid, r) }, enabled = !creatingCat) {
                        Text(if (creatingCat) "建着…" else "建一个", fontSize = 13.sp)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { suggest = null }, enabled = !creatingCat) {
                        Text("不用了", fontSize = 13.sp)
                    }
                },
            )
        }
    }
}

/** AI 页里的一张账单卡：左图标、中间分类+备注、右边金额，卡片下面两个胶囊按钮。 */
@Composable
private fun AiTxnCard(
    t: Txn,
    cat: Cat?,
    deleted: Boolean,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
) {
    val d = dayOf(t.at)
    Column(Modifier.fillMaxWidth()) {
        Text(
            "${d.monthValue}.${"%02d".format(d.dayOfMonth)} ${weekdayCn(d)} ${hhmm(t.at)}",
            fontSize = 11.sp, color = MiaoDim,
            modifier = Modifier.padding(start = 4.dp, bottom = 5.dp),
        )
        Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
            Row(
                Modifier.padding(horizontal = 12.dp, vertical = 11.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Bubble(catIcon(cat))
                Spacer(Modifier.width(11.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        cat?.name ?: "其它", fontSize = 15.sp, fontWeight = FontWeight.SemiBold,
                        color = MiaoInk, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    )
                    if (t.note.isNotBlank()) {
                        Spacer(Modifier.height(3.dp))
                        Text(
                            t.note, fontSize = 12.sp, color = MiaoDim,
                            maxLines = 1, overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    (if (t.kind == "in") "+" else "−") + fmt(t.cents),
                    fontSize = 16.sp, fontWeight = FontWeight.Bold,
                    color = if (t.kind == "in") MiaoGreen else MiaoInk,
                )
            }
        }
        if (deleted) {
            Text(
                "已删除", fontSize = 11.sp, color = MiaoDim,
                modifier = Modifier.padding(start = 4.dp, top = 6.dp),
            )
        } else {
            Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PillButton("修改账单") { onEdit() }
                PillButton("删除账单") { onDelete() }
            }
        }
    }
}

@Composable
private fun PillButton(text: String, onClick: () -> Unit) {
    Box(
        Modifier.background(Color.White, RoundedCornerShape(20.dp))
            .border(1.dp, MiaoLine, RoundedCornerShape(20.dp))
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 7.dp),
    ) { Text(text, fontSize = 12.sp, color = MiaoInkSoft) }
}

@Composable
private fun PromptChip(text: String, onClick: () -> Unit) {
    Surface(
        color = Color.White, shape = RoundedCornerShape(20.dp),
        modifier = Modifier.clickable { onClick() },
    ) {
        Text(text, fontSize = 11.sp, color = MiaoInkSoft, modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp))
    }
}

// ================================================================== 浮层
@Composable
private fun AddSheet(onVoice: () -> Unit, onKeypad: () -> Unit, onCalendar: () -> Unit) {
    SheetTitle("记一笔")
    Box(
        Modifier.fillMaxWidth().background(MiaoBlue, RoundedCornerShape(20.dp)).clickable { onVoice() }.padding(vertical = 18.dp),
        contentAlignment = Alignment.Center,
    ) { Text("🎙  说一句（最快）", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF)) }
    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetGhost("手打键盘", Modifier.weight(1f), onKeypad)
        SheetGhost("从日历里点", Modifier.weight(1f), onCalendar)
    }
    Spacer(Modifier.height(10.dp))
    Text(
        "说话比打字快，说错了还能改；在家在外面都能记，没网也一样。",
        fontSize = 10.sp, color = MiaoDim, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun VoiceSheet(onListen: () -> Unit, onCancel: () -> Unit) {
    SheetTitle("松手就记")
    Box(
        Modifier.fillMaxWidth().background(MiaoBlue, RoundedCornerShape(20.dp)).clickable { onListen() }.padding(vertical = 18.dp),
        contentAlignment = Alignment.Center,
    ) { Text("🎙  按一下说一句", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF)) }
    Spacer(Modifier.height(10.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        SheetGhost("取消", Modifier.weight(1f), onCancel)
    }
    Spacer(Modifier.height(8.dp))
    Text("例：“昨天中午吃饭 AA 68，用微信”", fontSize = 10.sp, color = MiaoDim, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
}

@Composable
private fun SheetGhost(label: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier.background(Color.White, RoundedCornerShape(14.dp))
            .border(1.dp, Color(0xFFE3E7EC), RoundedCornerShape(14.dp))
            .clickable { onClick() }.padding(vertical = 13.dp),
        contentAlignment = Alignment.Center,
    ) { Text(label, fontSize = 13.sp, color = MiaoInk) }
}

@Composable
private fun BookSheet(prefs: Prefs, txns: List<Txn>, api: Api, onPicked: (Long) -> Unit) {
    val ctx = LocalContext.current
    var adding by remember { mutableStateOf(false) }
    val month = YearMonth.now()
    SheetTitle("选账本")
    prefs.books.forEach { b ->
        val on = b.id == prefs.bookId
        val spent = txns.filter { it.bookId == b.id && it.kind == "out" && YearMonth.from(dayOf(it.at)) == month }.sumOf { it.cents }
        Row(
            Modifier.fillMaxWidth().padding(bottom = 8.dp)
                .background(if (on) Color(0xFFD9ECFC) else Color(0xFFF7F8FA), RoundedCornerShape(15.dp))
                .border(if (on) 1.5.dp else 0.dp, if (on) MiaoBlueLine else Color.Transparent, RoundedCornerShape(15.dp))
                .clickable { onPicked(b.id) }.padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(Modifier.size(34.dp).background(MiaoBlueSoft, RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) {
                Text(b.icon, fontSize = 16.sp)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(b.name, fontSize = 13.sp, color = MiaoInk)
                Text("本月 ${fmt(spent)}", fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(top = 1.dp))
            }
            if (on) Icon(Icons.Filled.Check, null, tint = MiaoBlueLine, modifier = Modifier.size(18.dp))
        }
    }
    Row(
        Modifier.fillMaxWidth().border(1.5.dp, Color(0xFFD9DEE5), RoundedCornerShape(15.dp))
            .clickable { adding = true }.padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(34.dp).background(Color(0xFFF2F4F7), RoundedCornerShape(11.dp)), contentAlignment = Alignment.Center) {
            Text("＋", fontSize = 15.sp, color = MiaoDim)
        }
        Spacer(Modifier.width(10.dp))
        Text("新建账本", fontSize = 13.sp, color = Color(0xFF8A9099))
    }

    if (adding) {
        var name by remember { mutableStateOf("") }
        var busy by remember { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { adding = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        if (name.isBlank()) return@TextButton
                        busy = true
                        Thread {
                            runCatching { api.createBook(name.trim()); api.syncMeta() }
                                .onSuccess { prefs.books.lastOrNull { it.name == name.trim() }?.let { b -> onPicked(b.id) } }
                                .onFailure { toast(ctx, "建账本失败：${it.message?.take(40)}") }
                            busy = false
                        }.start()
                    },
                    enabled = !busy && name.isNotBlank(),
                ) { Text(if (busy) "建着…" else "建") }
            },
            dismissButton = { TextButton(onClick = { adding = false }) { Text("取消") } },
            title = { Text("新建账本", fontSize = 15.sp) },
            text = {
                OutlinedTextField(name, { name = it }, singleLine = true,
                    placeholder = { Text("比如：装修 / 赡养老人", fontSize = 13.sp) })
            },
        )
    }
}

@Composable
private fun SearchSheet(prefs: Prefs, txns: List<Txn>, hidden: Boolean, onClose: () -> Unit) {
    var q by remember { mutableStateOf("") }
    val cats = prefs.cats.associateBy { it.id }
    val hit = if (q.isBlank()) emptyList() else txns.filter {
        (it.note.contains(q, true)) || (cats[it.catId ?: -1L]?.name?.contains(q, true) == true)
    }.take(30)
    SheetTitle("找一笔")
    Row(
        Modifier.fillMaxWidth().background(Color(0xFFF2F4F6), RoundedCornerShape(20.dp)).padding(horizontal = 14.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Filled.Search, null, tint = MiaoDim, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        BasicTextField(
            value = q, onValueChange = { q = it },
            textStyle = TextStyle(fontSize = 13.sp, color = MiaoInk),
            cursorBrush = SolidColor(MiaoGold),
            modifier = Modifier.weight(1f).padding(vertical = 10.dp),
            decorationBox = { inner -> Box { if (q.isEmpty()) Text("备注或分类名", fontSize = 13.sp, color = MiaoDim); inner() } },
        )
    }
    Spacer(Modifier.height(8.dp))
    if (q.isNotBlank() && hit.isEmpty()) Text("没找着", fontSize = 12.sp, color = MiaoDim, modifier = Modifier.padding(vertical = 8.dp))
    hit.forEach { t ->
        TxnRow(t, cats[t.catId ?: -1L], null, hidden)
        HorizontalDivider(color = MiaoLine)
    }
}
