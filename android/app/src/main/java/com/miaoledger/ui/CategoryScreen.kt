package com.miaoledger.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.data.Api
import com.miaoledger.data.ApiError
import com.miaoledger.data.Cat
import com.miaoledger.data.Prefs

private val CAT_ICONS = listOf("🍜", "🚌", "🛒", "🏠", "💊", "🧸", "✈", "🎁", "💼", "📚", "🎮", "📌")

/**
 * 分类配置：分「支出」「收入」两组，能加能删。
 * 删分类只影响以后选单，已经记过的账不动（统计里算「其它」），所以不用怕点错。
 */
@Composable
fun CategoryScreen(
    prefs: Prefs,
    api: Api,
    onBack: () -> Unit,
    onChanged: () -> Unit,
) {
    var tick by remember { mutableIntStateOf(0) }
    val cats = remember(tick) { prefs.cats }
    val outCats = cats.filter { it.kind != "in" }
    val inCats = cats.filter { it.kind == "in" }

    var askDelete by remember { mutableStateOf<Cat?>(null) }
    var err by remember { mutableStateOf<String?>(null) }

    var adding by remember { mutableStateOf(false) }
    var newName by remember { mutableStateOf("") }
    var newKind by remember { mutableStateOf("out") }
    var newIcon by remember { mutableStateOf(CAT_ICONS.first()) }
    var createBusy by remember { mutableStateOf(false) }
    var createErr by remember { mutableStateOf<String?>(null) }

    fun refreshMeta() {
        Thread {
            runCatching { api.syncMeta() }
            tick++
            onChanged()
        }.start()
    }

    fun deleteCat(c: Cat) {
        askDelete = null
        Thread {
            val e = runCatching { api.deleteCategory(c.id) }.exceptionOrNull()
            // 404 = 服务器上本来就没有了（可能在别的设备删过），当成功处理
            if (e != null && !(e is ApiError && e.notDeployed)) {
                err = (e as? ApiError)?.message ?: "这条没能删掉，等联网再试"
            }
            runCatching { api.syncMeta() }
            tick++
            onChanged()
        }.start()
    }

    fun createCat() {
        val name = newName.trim()
        createErr = when {
            name.isEmpty() -> "先给分类起个名字"
            name.length > 8 -> "名字短一点，8 个字以内"
            else -> null
        }
        if (createErr != null) return
        createBusy = true
        Thread {
            try {
                api.createCategory(name, newKind, newIcon)
                runCatching { api.syncMeta() }
                createBusy = false
                adding = false
                newName = ""
                tick++
                onChanged()
            } catch (e: Exception) {
                val ae = e as? ApiError
                createBusy = false
                createErr = when {
                    ae?.code == 409 -> "已经有这个分类了"
                    ae != null && ae.code == 0 -> "现在连不上服务器，等联网再加"
                    else -> ae?.message ?: "没加成，再试一次"
                }
            }
        }.start()
    }

    SecondPage(
        title = "分类",
        subtitle = "一共 ${cats.size} 个",
        onBack = onBack,
        scrollable = false,
        bottom = {
            Column {
                err?.let {
                    Text(it, fontSize = 11.sp, color = MiaoRed, modifier = Modifier.padding(horizontal = 18.dp, vertical = 4.dp))
                }
                Box(
                    Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 10.dp)
                        .background(MiaoBlue, RoundedCornerShape(14.dp))
                        .clickable { adding = true }.padding(vertical = 13.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("新增分类", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Color.White)
                }
            }
        },
    ) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
            CatGroup("支出", outCats) { askDelete = it }
            Spacer(Modifier.height(12.dp))
            CatGroup("收入", inCats) { askDelete = it }
            PageNote("点垃圾桶删掉一个分类。已经记过的账不会变，只是以后不再出现在选单里。")
            Spacer(Modifier.height(24.dp))
        }
    }

    // 删一个分类
    askDelete?.let { c ->
        AlertDialog(
            onDismissRequest = { askDelete = null },
            title = { Text("删掉「${c.name}」？", fontSize = 15.sp) },
            text = {
                Text(
                    "已经记过的账不会变，只是以后不再出现在选单里；这些账单在统计里显示为「其它」。",
                    fontSize = 13.sp, lineHeight = 20.sp,
                )
            },
            confirmButton = {
                TextButton(onClick = { deleteCat(c) }) { Text("删掉", color = MiaoRed, fontSize = 13.sp) }
            },
            dismissButton = { TextButton(onClick = { askDelete = null }) { Text("算了", fontSize = 13.sp) } },
        )
    }

    // 新增分类
    if (adding) {
        AlertDialog(
            onDismissRequest = { if (!createBusy) { adding = false; createErr = null } },
            title = { Text("新增一个分类", fontSize = 15.sp) },
            text = {
                Column {
                    Text("名字", fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(bottom = 4.dp))
                    Box(
                        Modifier.fillMaxWidth().background(MiaoBg, RoundedCornerShape(11.dp))
                            .border(1.dp, MiaoLine, RoundedCornerShape(11.dp)).padding(horizontal = 11.dp, vertical = 10.dp),
                    ) {
                        BasicTextField(
                            value = newName,
                            onValueChange = { newName = it.take(8) },
                            singleLine = true,
                            textStyle = TextStyle(fontSize = 14.sp, color = MiaoInk),
                            cursorBrush = SolidColor(MiaoInk),
                            modifier = Modifier.fillMaxWidth(),
                            decorationBox = { inner ->
                                if (newName.isEmpty()) Text("比如：宠物、装修", fontSize = 13.sp, color = MiaoDim)
                                inner()
                            },
                        )
                    }

                    Spacer(Modifier.height(12.dp))
                    Text("类型", fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(bottom = 4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        KindChip("支出", newKind == "out") { newKind = "out" }
                        KindChip("收入", newKind == "in") { newKind = "in" }
                    }

                    Spacer(Modifier.height(12.dp))
                    Text("图标", fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(bottom = 4.dp))
                    CAT_ICONS.chunked(6).forEach { rowIcons ->
                        Row(Modifier.padding(bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            rowIcons.forEach { e ->
                                Box(
                                    Modifier.size(36.dp)
                                        .background(if (e == newIcon) MiaoBlueSoft else MiaoBg, CircleShape)
                                        .border(1.dp, if (e == newIcon) MiaoBlueLine else MiaoLine, CircleShape)
                                        .clickable { newIcon = e },
                                    contentAlignment = Alignment.Center,
                                ) { Text(e, fontSize = 16.sp) }
                            }
                        }
                    }

                    createErr?.let {
                        Text(it, fontSize = 11.sp, color = MiaoRed, modifier = Modifier.padding(top = 10.dp))
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { if (!createBusy) createCat() }) {
                    Text(if (createBusy) "正在加…" else "加上", color = MiaoGreenDeep, fontSize = 13.sp)
                }
            },
            dismissButton = {
                TextButton(onClick = { if (!createBusy) { adding = false; createErr = null; newName = "" } }) {
                    Text("算了", fontSize = 13.sp)
                }
            },
        )
    }
}

@Composable
private fun CatGroup(label: String, list: List<Cat>, onDelete: (Cat) -> Unit) {
    CardLabel(label)
    Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
        if (list.isEmpty()) {
            EmptyHint("还没有${label}分类，点下面「新增分类」加一个。", "🌱")
        } else {
            Column {
                list.forEachIndexed { i, c ->
                    if (i > 0) HorizontalDivider(color = MiaoLine)
                    Row(
                        Modifier.fillMaxWidth().padding(start = 14.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(
                            Modifier.size(31.dp).background(MiaoBlueTint, RoundedCornerShape(10.dp)),
                            contentAlignment = Alignment.Center,
                        ) { Text(catIcon(c), fontSize = 15.sp) }
                        Spacer(Modifier.width(10.dp))
                        Text(c.name, fontSize = 13.sp, color = MiaoInk, modifier = Modifier.weight(1f))
                        Box(
                            Modifier.size(44.dp).clickable { onDelete(c) },
                            contentAlignment = Alignment.Center,
                        ) { Text("🗑", fontSize = 14.sp) }
                    }
                }
            }
        }
    }
}

@Composable
private fun KindChip(text: String, on: Boolean, onClick: () -> Unit) {
    Box(
        Modifier.height(34.dp).background(if (on) MiaoBlue else MiaoBg, RoundedCornerShape(10.dp))
            .border(1.dp, if (on) MiaoBlueLine else MiaoLine, RoundedCornerShape(10.dp))
            .clickable { onClick() }.padding(horizontal = 16.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, fontSize = 12.sp, color = if (on) Color.White else MiaoInk, fontWeight = if (on) FontWeight.Bold else FontWeight.Normal)
    }
}
