package com.miaoledger.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.BuildConfig
import com.miaoledger.data.Api
import com.miaoledger.data.LocalDb
import com.miaoledger.data.Prefs
import com.miaoledger.data.Sync

/**
 * 「我的」：只有四块——账号、备份、功能入口、版本号。
 * 不放设置入口，也不放退出登录：那些都在账号页里，免得点错。
 */
@Composable
fun MineScreen(
    prefs: Prefs,
    api: Api,
    db: LocalDb,
    onAccount: () -> Unit,
    onCategories: () -> Unit,
    onExport: () -> Unit,
    onChanged: () -> Unit,
) {
    val ctx = LocalContext.current
    var tick by remember { mutableIntStateOf(0) }
    var busy by remember { mutableStateOf(false) }
    var msg by remember { mutableStateOf<String?>(null) }
    val pending = remember(tick) { db.countPending() }
    val lastBackup = remember(tick) { prefs.lastBackupAt }
    val catCount = remember(tick) { prefs.cats.size }

    Column(Modifier.fillMaxSize().background(MiaoBg).statusBarsPadding()) {
        Row(
            Modifier.fillMaxWidth().padding(start = 18.dp, end = 18.dp, top = 12.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) { Text("我的", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk) }

        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = 18.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // ① 账号卡：点它进账号页（改密码 / 清空账单 / 退出登录都在里面）
            item {
                Surface(color = Color.White, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.fillMaxWidth().clickable { onAccount() }.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(43.dp).background(MiaoBlue, CircleShape), contentAlignment = Alignment.Center) {
                            Text(
                                (prefs.displayName.ifBlank { prefs.username }).take(1).ifBlank { "账" },
                                fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White,
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                prefs.displayName.ifBlank { prefs.username }, fontSize = 14.sp,
                                fontWeight = FontWeight.SemiBold, color = MiaoInk,
                            )
                            Text("账号 ${prefs.username}", fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(top = 2.dp))
                        }
                        Text("›", fontSize = 18.sp, color = MiaoDim)
                    }
                }
            }

            // ② 备份卡：服务器在哪、还差几笔没备份、什么时候备份过，都能一眼看到
            item { CardLabel("备份") }
            item {
                Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                    Column {
                        ValueLine(
                            title = "备份服务器地址",
                            value = prefs.server.ifBlank { "还没填" }.let { ellipsizeMiddle(it, 20, 8) },
                            dimValue = prefs.server.isBlank(),
                        )
                        HorizontalDivider(color = MiaoLine)
                        ValueLine(
                            title = "待备份账单",
                            badge = if (pending == 0) "已全部备份" else "$pending 笔",
                            badgeDim = pending == 0,
                            value = backupLabel(lastBackup),
                        )
                        HorizontalDivider(color = MiaoLine)
                        Box(
                            Modifier.fillMaxWidth().clickable {
                                if (busy) return@clickable
                                busy = true; msg = null
                                Thread {
                                    val r = Sync.run(prefs, db, api)
                                    msg = if (r.ok) {
                                        if (r.pushed > 0) "备份好了，传上去 ${r.pushed} 笔账" else "备份好了，账都已经在服务器上"
                                    } else {
                                        "现在连不上，等联网了会自己再备份"
                                    }
                                    busy = false
                                    tick++
                                    onChanged()
                                }.start()
                            }.padding(horizontal = 14.dp, vertical = 12.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                if (busy) "正在备份…" else "现在备份一下",
                                fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color.White,
                                modifier = Modifier.fillMaxWidth().background(MiaoBlue, RoundedCornerShape(12.dp))
                                    .padding(vertical = 10.dp), textAlign = TextAlign.Center,
                            )
                        }
                    }
                }
                msg?.let { Text(it, fontSize = 11.sp, color = MiaoDim, modifier = Modifier.padding(top = 6.dp, start = 4.dp)) }
                PageNote("每 6 小时自动备份一次，记完账也会补一次。没网就先存在手机上，联网了自己传。")
            }

            // ③ 功能卡：分类能自己配，账单能导出成表格
            item { Spacer(Modifier.height(2.dp)) }
            item {
                Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                    Column {
                        GroupRow(
                            "🏷", "分类配置",
                            if (catCount > 0) "一共 $catCount 个，点进去加" else "点进去加几个分类",
                            onClick = onCategories,
                        ) { Text("›", fontSize = 16.sp, color = MiaoDim) }
                        HorizontalDivider(color = MiaoLine)
                        GroupRow("📤", "导出账单", "存成 Excel 能打开的表格", onClick = onExport) {
                            Text("›", fontSize = 16.sp, color = MiaoDim)
                        }
                    }
                }
            }

            item {
                Text(
                    "小喵记账 ${BuildConfig.VERSION_NAME}", fontSize = 10.sp, color = MiaoDim,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
                )
            }
            item { Spacer(Modifier.height(22.dp)) }
        }
    }
}

/** 备份卡里的一行：左边标题（后面可带一个小角标），右边一句灰字。 */
@Composable
private fun ValueLine(
    title: String,
    value: String,
    badge: String? = null,
    badgeDim: Boolean = true,
    dimValue: Boolean = false,
) {
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(title, fontSize = 13.sp, color = MiaoInk)
        if (badge != null) {
            Spacer(Modifier.width(6.dp))
            Text(
                badge, fontSize = 10.sp,
                color = if (badgeDim) MiaoDim else MiaoBlueDeep,
                modifier = Modifier
                    .background(if (badgeDim) MiaoTrack else MiaoBlueNote, RoundedCornerShape(8.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp),
            )
        }
        Spacer(Modifier.weight(1f))
        Text(
            value, fontSize = 10.sp,
            color = if (dimValue) MiaoDim else MiaoDim,
            textAlign = TextAlign.End, maxLines = 1,
        )
    }
}
