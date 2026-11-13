package com.miaoledger.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId

// ================================================================== 二级页共用
/**
 * 二级页统一外壳：左上返回（44dp 热区）+ 标题 + 可选副标题。
 * 二级页的返回只回它的来源一级页，不直接跳明细——返回栈在 AppRoot 里管。
 */
@Composable
fun SecondPage(
    title: String,
    subtitle: String = "",
    onBack: () -> Unit,
    scrollable: Boolean = true,
    bottom: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Column(Modifier.fillMaxSize().background(MiaoBg).statusBarsPadding()) {
        Row(
            Modifier.fillMaxWidth().padding(start = 6.dp, end = 18.dp, top = 6.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack, modifier = Modifier.size(44.dp)) {
                Icon(Icons.Filled.ArrowBackIosNew, "返回", tint = MiaoInk, modifier = Modifier.size(18.dp))
            }
            Column(Modifier.weight(1f)) {
                Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
                if (subtitle.isNotEmpty()) {
                    Text(subtitle, fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(top = 1.dp))
                }
            }
        }
        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .let { m -> if (scrollable) m.padding(horizontal = 18.dp) else m },
            content = content,
        )
        // 底部操作区（比如「新增分类」那个大按钮）必须自己让开系统手势条 / 虚拟导航栏，
        // 否则会被压在下面点不到。放在这里统一处理，调用方不用再各自加 padding。
        if (bottom != null) {
            Column(Modifier.fillMaxWidth().navigationBarsPadding()) { bottom() }
        }
    }
}

/** 白卡里的一行：左边小图标 + 标题 + 一行灰字说明 + 右侧自定义尾部。整行可点（给了 onClick 时）。 */
@Composable
fun GroupRow(
    emoji: String,
    title: String,
    sub: String = "",
    onClick: (() -> Unit)? = null,
    iconBg: Color = MiaoBlueSoft,
    titleColor: Color = MiaoInk,
    trailing: @Composable () -> Unit = {},
) {
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable { onClick() } else it }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier.size(31.dp).background(iconBg, RoundedCornerShape(10.dp)),
            contentAlignment = Alignment.Center,
        ) { Text(emoji, fontSize = 15.sp) }
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontSize = 13.sp, color = titleColor)
            if (sub.isNotEmpty()) {
                Text(sub, fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(top = 1.dp))
            }
        }
        trailing()
    }
}

/** 二级页里的浅灰说明文字（10sp，跟在卡片下面）。 */
@Composable
fun PageNote(text: String) {
    Text(
        text, fontSize = 10.sp, color = MiaoDim, lineHeight = 15.sp,
        modifier = Modifier.padding(top = 6.dp, start = 4.dp, end = 4.dp),
    )
}

/** 「今天 14:20」「昨天 09:12」「11月3日 14:20」这种，比时间戳好懂。 */
fun backupLabel(ts: Long): String {
    if (ts <= 0L) return "还没备份过"
    val t = LocalDateTime.ofInstant(Instant.ofEpochMilli(ts), ZoneId.systemDefault())
    val today = LocalDate.now()
    val d = t.toLocalDate()
    val time = "%02d:%02d".format(t.hour, t.minute)
    return when {
        d == today -> "今天 $time"
        d == today.minusDays(1) -> "昨天 $time"
        d.year == today.year -> "${d.monthValue}月${d.dayOfMonth}日 $time"
        else -> "${d.year}年${d.monthValue}月${d.dayOfMonth}日"
    }
}

/** 中间省略：服务器地址太长时把中间挖掉，头和尾都留着（一眼能认出是哪个地址）。 */
fun ellipsizeMiddle(s: String, keepStart: Int = 18, keepEnd: Int = 10): String {
    if (s.length <= keepStart + keepEnd + 1) return s
    return s.take(keepStart) + "…" + s.takeLast(keepEnd)
}

/** 二级页里的一个空状态提示。 */
@Composable
fun EmptyHint(text: String, emoji: String = "🌱") {
    Column(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 22.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(emoji, fontSize = 22.sp)
        Text(text, fontSize = 11.sp, color = MiaoDim, lineHeight = 17.sp)
    }
}

/** 卡片标题（和一级页一致：11sp 灰字 + 左边留白）。 */
@Composable
fun CardLabel(text: String) {
    Text(text, fontSize = 11.sp, color = MiaoDim, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
}

/** 一行「标签：值」，用在账号信息块。 */
@Composable
fun InfoLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, fontSize = 12.sp, color = MiaoDim, modifier = Modifier.width(64.dp))
        Text(
            value, fontSize = 13.sp, color = MiaoInk, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f),
        )
    }
}
