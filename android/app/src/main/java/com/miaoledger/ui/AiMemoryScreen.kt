package com.miaoledger.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.data.AiMemory
import com.miaoledger.data.AiRule
import com.miaoledger.data.Api
import com.miaoledger.data.ApiError
import com.miaoledger.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * 「它的记忆」：AI 现在怎么认账、对你有什么印象、自己攒了哪些规矩。
 * 整页只读——它自己改自己，你不插手；实在觉得某条不对，可以删掉那一条。
 */
@Composable
fun AiMemoryScreen(
    prefs: Prefs,
    api: Api,
    onBack: () -> Unit,
    onChanged: () -> Unit,
) {
    var loading by remember { mutableStateOf(true) }
    var notReady by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    var mem by remember { mutableStateOf<AiMemory?>(null) }
    var askDelete by remember { mutableStateOf<AiRule?>(null) }
    var showPrompt by remember { mutableStateOf(false) }
    var version by remember { mutableIntStateOf(0) }

    LaunchedEffect(version) {
        loading = true
        notReady = false
        err = null
        try {
            val m = withContext(Dispatchers.IO) { api.aiMemory() }
            if (m != null) {
                mem = m
            } else {
                // 旧服务器没有 /ai/memory：退回用 /ai/rules + /ai/profile 拼出来，能看多少看多少
                val both = runCatching {
                    withContext(Dispatchers.IO) { api.rules() to api.profile() }
                }
                val pair = both.getOrNull()
                if (pair == null) {
                    notReady = true
                } else {
                    mem = AiMemory(
                        rules = pair.first,
                        rulesCount = pair.first.size,
                        hints = pair.second.hints,
                        version = pair.second.version,
                        updatedAt = pair.second.updatedAt,
                    )
                }
            }
        } catch (e: ApiError) {
            if (e.notDeployed) notReady = true else err = e.message
        } catch (e: Exception) {
            err = "没能读到。可能是网络断了，过会儿再试。"
        } finally {
            loading = false
        }
    }

    fun deleteRule(r: AiRule) {
        askDelete = null
        Thread {
            try {
                api.deleteRule(r.id)
                mem = mem?.copy(rules = mem?.rules.orEmpty().filterNot { it.id == r.id })
                onChanged()
            } catch (e: ApiError) {
                // 404 = 服务器上已经没了（可能在别的设备删过），当成功
                if (e.notDeployed) {
                    mem = mem?.copy(rules = mem?.rules.orEmpty().filterNot { it.id == r.id })
                    onChanged()
                } else {
                    err = e.message
                }
            } catch (e: Exception) {
                err = "这条没能删掉，再试一次。"
            }
        }.start()
    }

    SecondPage(title = "它的记忆", subtitle = "它自己改自己，你只管用", onBack = onBack) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
            when {
                loading -> Text(
                    "正在看它学了些什么…", fontSize = 12.sp, color = MiaoDim,
                    modifier = Modifier.padding(vertical = 20.dp, horizontal = 4.dp),
                )

                notReady -> Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text("服务器还没升级到这一版", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "这个页面要等服务器更新完才能用。现在记账不受影响。",
                            fontSize = 12.sp, color = MiaoDim, lineHeight = 18.sp,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "过会儿再看看", fontSize = 12.sp, color = MiaoGreenDeep,
                            modifier = Modifier.clickable { version++ }.padding(vertical = 6.dp),
                        )
                    }
                }

                err != null -> Surface(color = Color(0xFFFFF1F0), shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(err ?: "", fontSize = 12.sp, color = MiaoRed, lineHeight = 18.sp)
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "再试一次", fontSize = 12.sp, color = MiaoGreenDeep,
                            modifier = Modifier.clickable { err = null; version++ }.padding(vertical = 6.dp),
                        )
                    }
                }

                else -> {
                    val m = mem

                    // ① 它现在怎么认账
                    CardLabel("它现在怎么认账")
                    Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                        Column {
                            Text(
                                m?.how?.ifBlank { DEFAULT_HOW } ?: DEFAULT_HOW,
                                fontSize = 12.sp, color = MiaoInk, lineHeight = 19.sp,
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 13.dp),
                            )
                            val prompt = m?.prompt.orEmpty()
                            if (prompt.isNotBlank()) {
                                HorizontalDivider(color = MiaoLine)
                                Row(
                                    Modifier.fillMaxWidth().clickable { showPrompt = !showPrompt }.padding(horizontal = 14.dp, vertical = 11.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Text(
                                        if (showPrompt) "收起它的提示词" else "看它的提示词",
                                        fontSize = 12.sp, color = MiaoGreenDeep, modifier = Modifier.weight(1f),
                                    )
                                    Text(if (showPrompt) "▴" else "▾", fontSize = 11.sp, color = MiaoDim)
                                }
                                // 提示词会越来越长：给它自己的滚动区，别把整页撑爆，也别截断
                                if (showPrompt) {
                                    Box(
                                        Modifier.fillMaxWidth().heightIn(max = 260.dp)
                                            .background(MiaoBg).padding(horizontal = 12.dp, vertical = 10.dp),
                                    ) {
                                        Text(
                                            prompt,
                                            fontSize = 11.sp,
                                            fontFamily = FontFamily.Monospace,
                                            color = MiaoInkSoft,
                                            lineHeight = 16.sp,
                                            modifier = Modifier.verticalScroll(rememberScrollState()),
                                        )
                                    }
                                }
                            }
                        }
                    }
                    PageNote("这是它认账用的规矩，固定写在服务器上。你改不了，也不用改。")
                    Spacer(Modifier.height(12.dp))

                    // ② AI 对你的印象
                    CardLabel("AI 对你的印象")
                    Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 13.dp)) {
                            val hints = m?.hints.orEmpty()
                            Text(
                                if (hints.isNotBlank()) hints else "还没形成印象，多改几次它记的账。",
                                fontSize = 12.sp,
                                color = if (hints.isNotBlank()) MiaoInk else MiaoDim,
                                lineHeight = 19.sp,
                            )
                            Spacer(Modifier.height(6.dp))
                            Text(
                                "版本 v${m?.version.orEmpty().ifBlank { "?" }} · 学过 ${m?.feedbackCount ?: 0} 次",
                                fontSize = 10.sp, color = MiaoDim,
                            )
                        }
                    }
                    Spacer(Modifier.height(12.dp))

                    // ③ 它记住的规矩
                    CardLabel("它记住的规矩")
                    Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                        val rules = m?.rules.orEmpty()
                        if (rules.isEmpty()) {
                            EmptyHint("还没有规矩，你改一次它记的账就会有一条。", "🌱")
                        } else {
                            Column {
                                rules.forEachIndexed { i, r ->
                                    if (i > 0) HorizontalDivider(color = MiaoLine)
                                    RuleRow(r) { askDelete = r }
                                }
                            }
                        }
                    }
                    PageNote("这些是它自己学出来的。看着不对可以删掉，删了它就不再照这条来。")
                    Spacer(Modifier.height(14.dp))

                    // ④ 页脚
                    Text(
                        "想改它的判断方式，让维护的人直接改后端提示词。",
                        fontSize = 10.sp, color = MiaoDim, lineHeight = 15.sp,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
                    )
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }

    askDelete?.let { r ->
        AlertDialog(
            onDismissRequest = { askDelete = null },
            title = { Text("删掉这条？", fontSize = 15.sp) },
            text = {
                Text(
                    "「${r.pattern}」以后就不再自动归到「${r.targetName}」了。之前的账不受影响。",
                    fontSize = 13.sp, lineHeight = 20.sp,
                )
            },
            confirmButton = { TextButton(onClick = { deleteRule(r) }) { Text("删掉", color = MiaoRed, fontSize = 13.sp) } },
            dismissButton = { TextButton(onClick = { askDelete = null }) { Text("算了", fontSize = 13.sp) } },
        )
    }
}

private const val DEFAULT_HOW =
    "你说一句「买咖啡 25」，它先认出这是花钱、多少钱、属于哪类，记到你上次用的账户上。" +
        "认错了你改一次，它就把「这句话 → 你选的分类」记成一条规矩，下次同样的话直接照那条来。"

private fun kindEmoji(kind: String): String = when (kind) {
    "account" -> "💳"
    "book" -> "📒"
    else -> "🏷"
}

private fun kindLabel(kind: String): String = when (kind) {
    "account" -> "账户"
    "book" -> "账本"
    else -> "分类"
}

@Composable
private fun RuleRow(r: AiRule, onDelete: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(30.dp).background(MiaoBlueTint, RoundedCornerShape(10.dp)),
            contentAlignment = Alignment.Center,
        ) { Text(kindEmoji(r.kind), fontSize = 13.sp) }
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
            Text(r.pattern, fontSize = 13.sp, color = MiaoInk, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(2.dp))
            Text(
                "${kindLabel(r.kind)}记成「${r.targetName}」" + if (r.hits > 0) " · 按这条归过 ${r.hits} 次" else "",
                fontSize = 10.sp, color = MiaoDim,
            )
        }
        Box(Modifier.size(44.dp).clickable { onDelete() }, contentAlignment = Alignment.Center) {
            Text("🗑", fontSize = 14.sp)
        }
    }
}
