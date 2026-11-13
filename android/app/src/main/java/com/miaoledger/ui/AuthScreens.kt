package com.miaoledger.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBackIosNew
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoledger.BuildConfig
import com.miaoledger.data.Api
import com.miaoledger.data.ApiError
import com.miaoledger.data.Prefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// 服务器地址不预置任何真实主机：首次使用时由使用者在「高级设置」里自己填。
// 留空就提示一个通用示例，填不填、填什么都由使用者决定。
private const val SERVER_EXAMPLE = "http://server.local:8000"
private val USERNAME_RE = Regex("^[A-Za-z0-9_]{2,20}$")

/**
 * 没登录时看到的一切：欢迎页 → 登录 / 创建账号（分四步）/ 忘记密码。
 * 服务器地址收在欢迎页的「高级设置」里，平时不用管。
 */
@Composable
fun AuthFlow(prefs: Prefs, api: Api, onDone: () -> Unit) {
    var page by remember { mutableStateOf("welcome") } // welcome / login / register / forgot
    var server by remember { mutableStateOf(prefs.server) }
    fun useServer() {
        val s = server.trim()
        server = s
        prefs.server = s
    }

    when (page) {
        "login" -> LoginPage(
            prefs = prefs,
            api = api,
            server = server,
            initialUser = prefs.username,
            onBack = { page = "welcome" },
            onRegister = { page = "register" },
            onForgot = { page = "forgot" },
            onDone = onDone,
            beforeCall = { useServer() },
        )
        "register" -> RegisterPage(
            prefs = prefs,
            api = api,
            initialUser = prefs.username,
            onBack = { page = "welcome" },
            onLogin = { page = "login" },
            onDone = onDone,
            beforeCall = { useServer() },
        )
        "forgot" -> ForgotPage(
            prefs = prefs,
            server = server,
            onBack = { page = "login" },
        )
        else -> WelcomePage(
            server = server,
            onServer = { server = it },
            onLogin = { page = "login" },
            onRegister = { page = "register" },
        )
    }
}

// ------------------------------------------------------------------ 欢迎页
@Composable
private fun WelcomePage(
    server: String,
    onServer: (String) -> Unit,
    onLogin: () -> Unit,
    onRegister: () -> Unit,
) {
    var advanced by remember { mutableStateOf(false) }
    Column(
        Modifier.fillMaxSize().background(MiaoBg).statusBarsPadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 20.dp),
    ) {
        Spacer(Modifier.height(46.dp))
        Text("小喵记账", fontSize = 30.sp, fontWeight = FontWeight.Bold, color = MiaoInk)
        Spacer(Modifier.height(8.dp))
        Text("两个人的账，简单记清楚。", fontSize = 15.sp, color = MiaoInkSoft)

        Spacer(Modifier.height(22.dp))
        Surface(color = MiaoBlue, shape = RoundedCornerShape(22.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(horizontal = 18.dp, vertical = 18.dp)) {
                Text("账存在哪儿？", fontSize = 12.sp, color = Color(0xCCFFFFFF))
                Spacer(Modifier.height(5.dp))
                Text(
                    "存在这部手机里，另外备份一份到你自己的服务器。不上外面的云，也不给任何人看。",
                    fontSize = 14.sp, color = Color(0xFFFFFFFF), lineHeight = 21.sp,
                )
            }
        }

        Spacer(Modifier.height(26.dp))
        BrandButton("登录", primary = true) { onLogin() }
        Spacer(Modifier.height(10.dp))
        BrandButton("创建账号") { onRegister() }
        Spacer(Modifier.height(10.dp))
        Text(
            "第一次用？得先向已经装好服务端的人要一串邀请码，没有邀请码建不了账号。",
            fontSize = 11.sp, color = MiaoDim, lineHeight = 17.sp,
            modifier = Modifier.padding(horizontal = 2.dp),
        )

        Spacer(Modifier.height(18.dp))
        Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
            Column {
                Row(
                    Modifier.fillMaxWidth().clickable { advanced = !advanced }
                        .padding(horizontal = 14.dp, vertical = 13.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text("高级设置", fontSize = 13.sp, color = MiaoInkSoft, modifier = Modifier.weight(1f))
                    Text(if (advanced) "收起" else "展开", fontSize = 11.sp, color = MiaoDim)
                }
                if (advanced) {
                    Column(Modifier.padding(start = 14.dp, end = 14.dp, bottom = 12.dp)) {
                        OutlinedTextField(
                            value = server, onValueChange = onServer,
                            label = { Text("服务器地址", fontSize = 11.sp) },
                            singleLine = true, modifier = Modifier.fillMaxWidth(),
                            textStyle = TextStyle(fontSize = 13.sp),
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "填你自己服务器的地址，局域网 IP、内网穿透地址都行。\n例如 $SERVER_EXAMPLE",
                            fontSize = 10.sp, color = MiaoDim, lineHeight = 15.sp,
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(26.dp))
        Text(
            "版本 ${BuildConfig.VERSION_NAME} · 两个人的记账本",
            fontSize = 10.sp, color = Color(0xFFB6BBC2),
            modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(24.dp))
    }
}

// ------------------------------------------------------------------ 登录
@Composable
private fun LoginPage(
    prefs: Prefs,
    api: Api,
    server: String,
    initialUser: String,
    onBack: () -> Unit,
    onRegister: () -> Unit,
    onForgot: () -> Unit,
    onDone: () -> Unit,
    beforeCall: () -> Unit,
) {
    var user by remember { mutableStateOf(initialUser) }
    var pin by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    fun submit() {
        if (busy) return
        busy = true
        err = null
        beforeCall()
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.login(server, user.trim(), pin)
                    api.syncMeta()
                }
                onDone()
            } catch (e: Exception) {
                err = (e as? ApiError)?.message ?: "没登进去，再试一次。"
            } finally {
                busy = false
            }
        }
    }

    AuthScaffold(onBack = onBack, title = "登录", subtitle = "用你自己的账号，别人看不到你的账") {
        AuthField(user, { user = it }, "账号", hint = "注册时用的小写字母或数字")
        Spacer(Modifier.height(10.dp))
        AuthField(
            pin, { pin = it }, "密码", hint = "当时设的数字密码",
            number = true, password = true,
        )
        Spacer(Modifier.height(18.dp))
        BrandButton(if (busy) "正在登…" else "登录", primary = true, enabled = !busy && user.isNotBlank() && pin.length >= 4) {
            submit()
        }
        err?.let { ErrorBox(it) }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(onClick = onForgot) { Text("忘记密码了？", fontSize = 12.sp, color = MiaoInkSoft) }
            TextButton(onClick = onRegister) { Text("还没有账号，创建一个", fontSize = 12.sp, color = MiaoInkSoft) }
        }
    }
}

// ------------------------------------------------------------------ 注册（分四步）
@Composable
private fun RegisterPage(
    prefs: Prefs,
    api: Api,
    initialUser: String,
    onBack: () -> Unit,
    onLogin: () -> Unit,
    onDone: () -> Unit,
    beforeCall: () -> Unit,
) {
    var step by remember { mutableStateOf(1) }
    var code by remember { mutableStateOf("") }
    var user by remember { mutableStateOf(initialUser) }
    var nick by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    var pin2 by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }

    // 账号名合不合规、有没有被占
    var checkText by remember { mutableStateOf<String?>(null) }
    var checkOk by remember { mutableStateOf<Boolean?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(step, user) {
        if (step != 2) return@LaunchedEffect
        val u = user.trim()
        checkOk = null
        checkText = null
        if (!USERNAME_RE.matches(u)) {
            checkText = "2–20 个字符，只能用英文字母、数字和下划线"
            return@LaunchedEffect
        }
        delay(450)
        beforeCall()
        try {
            val r = withContext(Dispatchers.IO) { api.checkUsername(u) }
            checkOk = r.available
            checkText = if (r.available) "可以用" else (r.reason ?: "这个账号名已经有人用了，换一个")
        } catch (e: ApiError) {
            // 服务端还没这个接口 / 暂时连不上：先不拦着
            checkOk = null
            checkText = if (e.notDeployed) "服务器还说不上能不能用，先往下走" else "现在连不上服务器，等注册时会再查一次"
        } catch (e: Exception) {
            checkOk = null
            checkText = "现在查不了，先往下走"
        }
    }

    fun stepTitle() = when (step) {
        1 -> "第一步：邀请码"
        2 -> "第二步：账号名"
        3 -> "第三步：怎么称呼你"
        else -> "第四步：设个密码"
    }

    fun stepSub() = when (step) {
        1 -> "邀请码向已经装好这个 App 的人要，一串字母和横杠。"
        2 -> "以后登录用它。小写字母、数字、下划线都行，2 到 20 个字符。"
        3 -> "这是别人看到的名字，别人就按这个叫你。"
        else -> "正好 6 位数字，别用生日。忘了可以找管理员重置。"
    }

    fun submit() {
        if (busy) return
        if (pin.length != 6 || pin.any { !it.isDigit() }) { err = "密码要正好 6 位数字。"; return }
        if (pin != pin2) { err = "两次输的密码不一样，再对一遍。"; return }
        busy = true
        err = null
        beforeCall()
        scope.launch {
            try {
                withContext(Dispatchers.IO) {
                    api.register(prefs.server, user.trim(), pin, code.trim(), nick.trim())
                    api.syncMeta()
                }
                onDone()
            } catch (e: Exception) {
                err = (e as? ApiError)?.message ?: "账号没建起来，再试一次。"
            } finally {
                busy = false
            }
        }
    }

    fun goNext() {
        err = null
        when (step) {
            1 -> if (code.isBlank()) err = "邀请码还没填。" else step = 2
            2 -> when {
                !USERNAME_RE.matches(user.trim()) -> err = "账号名要 2–20 个字符，只能用英文字母、数字和下划线。"
                checkOk == false -> err = checkText ?: "这个账号名已经有人用了，换一个。"
                else -> {
                    if (nick.isBlank()) nick = user.trim()
                    step = 3
                }
            }
            3 -> if (nick.isBlank()) err = "写个称呼吧，一两个字也行。" else step = 4
            else -> submit()
        }
    }

    AuthScaffold(onBack = { if (step > 1) { step -= 1; err = null } else onBack() }, title = stepTitle(), subtitle = stepSub()) {
        StepDots(step)
        Spacer(Modifier.height(14.dp))
        when (step) {
            1 -> AuthField(code, { code = it }, "邀请码", hint = "比如 XIAOMIAO-2026")
            2 -> {
                AuthField(user, { user = it }, "账号名", hint = "只用英文字母、数字、下划线")
                checkText?.let {
                    val color = when (checkOk) {
                        true -> MiaoGreenDeep
                        false -> MiaoRed
                        else -> MiaoDim
                    }
                    Row(Modifier.padding(top = 6.dp, start = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (checkOk == true) {
                            Icon(Icons.Filled.Check, null, tint = color, modifier = Modifier.size(13.dp))
                            Spacer(Modifier.width(4.dp))
                        }
                        Text(it, fontSize = 11.sp, color = color)
                    }
                }
            }
            3 -> AuthField(nick, { nick = it }, "称呼", hint = "比如：小张 / 阿宝")
            else -> {
                AuthField(pin, { pin = it.filter(Char::isDigit).take(6) }, "密码", hint = "正好 6 位数字", number = true, password = true)
                Spacer(Modifier.height(10.dp))
                AuthField(pin2, { pin2 = it.filter(Char::isDigit).take(6) }, "再输一遍密码", hint = "确认没按错", number = true, password = true)
            }
        }
        Spacer(Modifier.height(20.dp))
        BrandButton(
            text = when {
                step < 4 -> "下一步"
                busy -> "正在创建…"
                else -> "完成，开始记账"
            },
            primary = true,
            enabled = !busy,
        ) { goNext() }
        if (step == 1) {
            Spacer(Modifier.height(10.dp))
            Text(
                "邀请码是管理员自己设的，不是手机号也不是验证码。",
                fontSize = 11.sp, color = MiaoDim, lineHeight = 17.sp,
            )
        }
        err?.let { ErrorBox(it) }
        Spacer(Modifier.height(10.dp))
        TextButton(onClick = onLogin, modifier = Modifier.fillMaxWidth()) {
            Text("已经有账号了，去登录", fontSize = 12.sp, color = MiaoInkSoft)
        }
    }
}

@Composable
private fun StepDots(step: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        (1..4).forEach { i ->
            Box(
                Modifier.size(width = if (i == step) 22.dp else 8.dp, height = 8.dp)
                    .background(if (i <= step) MiaoBlueLine else Color(0xFFE1E5EA), RoundedCornerShape(4.dp))
            )
        }
        Spacer(Modifier.width(4.dp))
        Text("$step / 4", fontSize = 10.sp, color = MiaoDim)
    }
}

// ------------------------------------------------------------------ 忘记密码
@Composable
private fun ForgotPage(prefs: Prefs, server: String, onBack: () -> Unit) {
    AuthScaffold(onBack = onBack, title = "忘记密码了", subtitle = "密码没法自己改，得找管理员帮你重置") {
        Surface(color = Color.White, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ForgotStep("1", "跟管理员说一声，报你的账号名：${prefs.username.ifBlank { "（就是登录用的那个）" }}")
                ForgotStep("2", "管理员会在服务器上运行：python -m app.cli reset-pin 你的账号 新密码")
                ForgotStep("3", "重置完，旧手机上的登录会失效。回到这里用新密码登录就行。")
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            "服务器现在填的是：$server\n地址填错或服务器没启动时会连不上，检查一下再试。",
            fontSize = 11.sp, color = MiaoDim, lineHeight = 17.sp,
        )
        Spacer(Modifier.height(18.dp))
        BrandButton("回去登录", primary = true) { onBack() }
    }
}

@Composable
private fun ForgotStep(n: String, text: String) {
    Row(verticalAlignment = Alignment.Top) {
        Box(
            Modifier.size(20.dp).background(MiaoBlue, CircleShape),
            contentAlignment = Alignment.Center,
        ) { Text(n, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFFFFFFFF)) }
        Spacer(Modifier.width(9.dp))
        Text(text, fontSize = 12.sp, color = MiaoInkSoft, lineHeight = 18.sp)
    }
}

// ------------------------------------------------------------------ 小零件
@Composable
private fun AuthScaffold(
    onBack: () -> Unit,
    title: String,
    subtitle: String,
    content: @Composable () -> Unit,
) {
    Column(
        Modifier.fillMaxSize().background(MiaoBg).statusBarsPadding()
            .verticalScroll(rememberScrollState()).padding(horizontal = 20.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack, modifier = Modifier.size(44.dp)) {
                Icon(Icons.Filled.ArrowBackIosNew, "返回", tint = MiaoInk, modifier = Modifier.size(18.dp))
            }
            Spacer(Modifier.weight(1f))
        }
        Spacer(Modifier.height(6.dp))
        Text(title, fontSize = 23.sp, fontWeight = FontWeight.Bold, color = MiaoInk)
        Spacer(Modifier.height(6.dp))
        Text(subtitle, fontSize = 12.sp, color = MiaoDim, lineHeight = 18.sp)
        Spacer(Modifier.height(18.dp))
        content()
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun AuthField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    hint: String,
    number: Boolean = false,
    password: Boolean = false,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label, fontSize = 12.sp) },
        placeholder = { Text(hint, fontSize = 12.sp, color = Color(0xFFB6BBC2)) },
        singleLine = true,
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = KeyboardOptions(
            keyboardType = if (number) KeyboardType.NumberPassword else KeyboardType.Text,
        ),
        textStyle = TextStyle(fontSize = 14.sp, color = MiaoInk),
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun BrandButton(
    text: String,
    primary: Boolean = false,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    if (primary) {
        Button(
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = MiaoBlue,
                contentColor = Color(0xFFFFFFFF),
                disabledContainerColor = MiaoBlueSoft,
                disabledContentColor = Color(0x80FFFFFF),
            ),
        ) {
            Text(text, fontSize = 15.sp, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    } else {
        Box(
            Modifier.fillMaxWidth().height(50.dp)
                .background(Color.White, RoundedCornerShape(16.dp))
                .border(1.dp, MiaoLine, RoundedCornerShape(16.dp))
                .clickable(enabled = enabled) { onClick() },
            contentAlignment = Alignment.Center,
        ) {
            Text(text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = MiaoInk)
        }
    }
}

@Composable
private fun ErrorBox(msg: String) {
    Spacer(Modifier.height(10.dp))
    Surface(color = Color(0xFFFFF1F0), shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Text(
            msg, fontSize = 12.sp, color = MiaoRed, lineHeight = 18.sp,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
        )
    }
}
