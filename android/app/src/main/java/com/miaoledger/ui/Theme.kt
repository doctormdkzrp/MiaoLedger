package com.miaoledger.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// 亮色基调：主色淡蓝 + 冷灰页面底 + 白卡 + 暖橙图表 + 绿（收入）/ 红（支出）
// 主色只用来「指出可点的东西」，大面积仍是白卡，避免整屏发蓝。

// -- 品牌色 --
val MiaoBlue = Color(0xFF5AA9F0)
val MiaoBlueDeep = Color(0xFF2C7BC4)
val MiaoBlueSoft = Color(0xFFD9ECFC)
val MiaoBlueLine = Color(0xFFA9D4F7)
val MiaoBlueTint = Color(0xFFF1F8FE)
val MiaoBlueNote = Color(0xFFEAF4FD)

// -- 中性色 --
val MiaoBg = Color(0xFFF2F5F9)
val MiaoCard = Color(0xFFFFFFFF)
val MiaoInk = Color(0xFF2B3440)
val MiaoInkSoft = Color(0xFF5C6672)
val MiaoDim = Color(0xFF98A1AB)
val MiaoLine = Color(0xFFE8EDF3)
val MiaoSegBg = Color(0xFFE4EAF2)
val MiaoTrack = Color(0xFFEDF1F6)
val MiaoBottomBar = Color(0xFFFFFFFF)

// -- 语义色 --
val MiaoOrange = Color(0xFFF2A65A)
val MiaoOrangeBar = Color(0xFFF7C177)
val MiaoGreen = Color(0xFF3FAE78)
val MiaoGreenDeep = Color(0xFF2C7A57)
val MiaoGreenSoft = Color(0xFFE4F5EC)
val MiaoRed = Color(0xFFE85C55)
val MiaoGold = Color(0xFFB07A00)
val MiaoWarn = Color(0xFFE0A32B)
val MiaoPink = Color(0xFFEE8FA8)

private val colors = lightColorScheme(
    primary = MiaoBlue,
    onPrimary = Color.White,
    primaryContainer = MiaoBlueSoft,
    onPrimaryContainer = MiaoBlueDeep,
    secondary = MiaoBlueDeep,
    onSecondary = Color.White,
    background = MiaoBg,
    onBackground = MiaoInk,
    surface = MiaoCard,
    onSurface = MiaoInk,
    surfaceVariant = Color(0xFFEDF1F6),
    onSurfaceVariant = MiaoDim,
)

private val type = Typography(
    headlineLarge = TextStyle(fontSize = 34.sp, fontWeight = FontWeight.Bold, color = MiaoInk),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk),
    bodyMedium = TextStyle(fontSize = 14.sp, color = MiaoInk),
    bodySmall = TextStyle(fontSize = 12.sp, color = MiaoDim),
)

@Composable
fun MiaoTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = colors, typography = type, content = content)
}
