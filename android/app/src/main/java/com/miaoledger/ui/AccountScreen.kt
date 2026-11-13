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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.data.Api
import com.miaoledger.data.ApiError
import com.miaoledger.data.LocalDb
import com.miaoledger.data.Prefs
import com.miaoledger.data.Sync

/**
 * 账号页：改密码、清空账单、退出登录都收在这里。
 * 这三个动作都会动到「登录状态」或「全部账」，所以不放在一级页上，点进来再做。
 */
@Composable
fun AccountScreen(
    prefs: Prefs,
    api: Api,
    db: LocalDb,
    onBack: () -> Unit,
    onWiped: () -> Unit,
    onLogout: () -> Unit,
) {
    var pinOpen by remember { mutableStateOf(false) }
    var oldPin by remember { mutableStateOf("") }
    var newPin by remember { mutableStateOf("") }
    var newPin2 by remember { mutableStateOf("") }
    var pinBusy by remember { mutableStateOf(false) }
    var pinMsg by remember { mutableStateOf<String?>(null) }
    var pinErr by remember { mutableStateOf<String?>(null) }

    var askWipe1 by remember { mutableStateOf(false) }
    var askWipe2 by remember { mutableStateOf(false) }
    var wiping by remember { mutableStateOf(false) }
    var askLogout by remember { mutableStateOf(false) }
    val total = remember { db.countAll() }

    fun resetPinForm() {
        oldPin = ""; newPin = ""; newPin2 = ""; pinMsg = null; pinErr = null
    }

    fun submitPin() {
        pinErr = null
        pinMsg = null
        when {
            oldPin.isBlank() -> { pinErr = "先填现在的密码"; return }
            newPin.length != 6 || newPin.any { !it.isDigit() } -> { pinErr = "新密码要正好 6 位数字"; return }
            newPin != newPin2 -> { pinErr = "两次输的新密码不一样，再对一下"; return }
            newPin == oldPin -> { pinErr = "新密码和现在的密码一样，换一个"; return }
        }
        pinBusy = true
        Thread {
            runCatching { api.changePin(oldPin, newPin) }
                .onSuccess { revoked ->
                    resetPinForm()
                    pinMsg = buildString {
                        append("密码改好了，下次用新密码登录。")
                        if (revoked > 0) append("\n其它手机上的登录已失效，需要用新密码重新登录。")
                    }
                    pinOpen = false
                }
                .onFailure { e ->
                    pinErr = when (e) {
                        is ApiError -> if (e.code == 422) e.detail ?: "新密码要正好 6 位数字" else e.message
                        else -> "改不了，等联网再试"
                    }
                }
            pinBusy = false
        }.start()
    }

    fun doWipe() {
        wiping = true
        // 手机上先清干净：账、AI 改账记录都删掉，别留半份
        db.deleteAll()
        prefs.lastPullAt = 0
        Thread {
            val ok = runCatching { api.wipeTxns() }.isSuccess
            // 没网就记一笔：下次备份开头先去服务器把那半份删掉，免得两边不一致
            if (!ok) prefs.pendingWipe = true
            wiping = false
            onWiped()
        }.start()
    }

    SecondPage(title = "账号", onBack = onBack, scrollable = false) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
            Spacer(Modifier.height(2.dp))

            // 身份
            Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    InfoLine("昵称", prefs.displayName.ifBlank { prefs.username })
                    HorizontalDivider(color = MiaoLine)
                    InfoLine("账号", prefs.username)
                    HorizontalDivider(color = MiaoLine)
                    InfoLine("服务器", prefs.server)
                }
            }
            PageNote("昵称是给自己看的，账号才是登录用的。")
            Spacer(Modifier.height(12.dp))

            // 操作
            Surface(color = Color.White, shape = RoundedCornerShape(17.dp), modifier = Modifier.fillMaxWidth()) {
                Column {
                    GroupRow(
                        "🔑", "修改密码", if (pinOpen) "填完点「改好了」" else "6 位数字，改了要记住",
                        onClick = { pinOpen = !pinOpen; if (!pinOpen) resetPinForm() },
                    ) { Text(if (pinOpen) "收起" else "›", fontSize = 11.sp, color = MiaoDim) }

                    if (pinOpen) {
                        Column(Modifier.padding(start = 14.dp, end = 14.dp, bottom = 12.dp)) {
                            PinField("现在的密码", oldPin) { oldPin = it }
                            Spacer(Modifier.height(8.dp))
                            PinField("新密码（6 位数字）", newPin) { newPin = it }
                            Spacer(Modifier.height(8.dp))
                            PinField("再输一次新密码", newPin2) { newPin2 = it }
                            pinErr?.let {
                                Text(it, fontSize = 11.sp, color = MiaoRed, lineHeight = 17.sp, modifier = Modifier.padding(top = 8.dp))
                            }
                            Spacer(Modifier.height(10.dp))
                            Box(
                                Modifier.fillMaxWidth().clickable { if (!pinBusy) submitPin() }
                                    .background(MiaoBlue, RoundedCornerShape(12.dp)).padding(vertical = 11.dp),
                                contentAlignment = Alignment.Center,
                            ) {
                                Text(
                                    if (pinBusy) "正在改…" else "改好了",
                                    fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color.White,
                                )
                            }
                        }
                    }

                    pinMsg?.let {
                        HorizontalDivider(color = MiaoLine)
                        Text(
                            it, fontSize = 11.sp, color = MiaoGreenDeep, lineHeight = 17.sp,
                            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                        )
                    }

                    HorizontalDivider(color = MiaoLine)
                    GroupRow(
                        "🧹", "清空所有账单",
                        if (total > 0) "一共 $total 笔，清空后不能恢复" else "现在没有账单",
                        onClick = { if (total > 0 && !wiping) askWipe1 = true },
                        titleColor = if (total > 0) MiaoRed else MiaoDim,
                    ) { Text(if (wiping) "正在清…" else "", fontSize = 11.sp, color = MiaoDim) }

                    HorizontalDivider(color = MiaoLine)
                    GroupRow("↩", "退出登录", "换人用这台手机时点这儿", onClick = { askLogout = true }, titleColor = MiaoRed) {
                        Text("")
                    }
                }
            }
            PageNote("清空只删账单，不会删掉 AI 学到的规矩。")
            Spacer(Modifier.height(24.dp))
        }
    }

    if (askWipe1) {
        AlertDialog(
            onDismissRequest = { askWipe1 = false },
            title = { Text("清空所有账单？", fontSize = 15.sp) },
            text = {
                Text(
                    "一共 $total 笔，清空后手机和服务器上的备份都会没有，且不能恢复。",
                    fontSize = 13.sp, lineHeight = 20.sp,
                )
            },
            confirmButton = {
                TextButton(onClick = { askWipe1 = false; askWipe2 = true }) {
                    Text("我要清空", color = MiaoRed, fontSize = 13.sp)
                }
            },
            dismissButton = { TextButton(onClick = { askWipe1 = false }) { Text("算了", fontSize = 13.sp) } },
        )
    }

    if (askWipe2) {
        AlertDialog(
            onDismissRequest = { askWipe2 = false },
            title = { Text("真的要清空吗？", fontSize = 15.sp) },
            text = { Text("输入框不需要，点「确认清空」后立即删除。", fontSize = 13.sp, lineHeight = 20.sp) },
            confirmButton = {
                TextButton(onClick = { askWipe2 = false; doWipe() }) {
                    Text("确认清空", color = MiaoRed, fontSize = 13.sp)
                }
            },
            dismissButton = { TextButton(onClick = { askWipe2 = false }) { Text("算了", fontSize = 13.sp) } },
        )
    }

    if (askLogout) {
        AlertDialog(
            onDismissRequest = { askLogout = false },
            title = { Text("退出登录？", fontSize = 15.sp) },
            text = { Text("账都还在手机上，不会丢。下次用账号和密码登回来就行。", fontSize = 13.sp, lineHeight = 20.sp) },
            confirmButton = {
                TextButton(onClick = { askLogout = false; onLogout() }) {
                    Text("退出", color = MiaoRed, fontSize = 13.sp)
                }
            },
            dismissButton = { TextButton(onClick = { askLogout = false }) { Text("算了", fontSize = 13.sp) } },
        )
    }
}

/** 密码输入：只收数字、不要键盘以外的花样。 */
@Composable
private fun PinField(label: String, value: String, onChange: (String) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Text(label, fontSize = 10.sp, color = MiaoDim, modifier = Modifier.padding(start = 2.dp, bottom = 4.dp))
        Box(
            Modifier.fillMaxWidth().background(MiaoBg, RoundedCornerShape(12.dp))
                .border(1.dp, MiaoLine, RoundedCornerShape(12.dp)).padding(horizontal = 12.dp, vertical = 11.dp),
        ) {
            BasicTextField(
                value = value,
                onValueChange = { s -> onChange(s.filter { it.isDigit() }.take(32)) },
                singleLine = true,
                textStyle = TextStyle(fontSize = 15.sp, color = MiaoInk),
                cursorBrush = SolidColor(MiaoInk),
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth(),
                decorationBox = { inner ->
                    if (value.isEmpty()) Text("6 位数字", fontSize = 14.sp, color = MiaoDim)
                    inner()
                },
            )
        }
    }
}
