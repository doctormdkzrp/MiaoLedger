import java.io.File
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// ---------------------------------------------------------------- release 签名
// 密钥由需求方自己生成、自己保管，不进仓库。
// 构建时从仓库根（或 android/）的 keystore.properties 读，该文件已被 .gitignore 忽略；
// 仓库里只提交 android/keystore.properties.example 占位。
// 文件不存在或某项没填时，只有打 release 会停下来报人话，debug 包不受任何影响。

// rootProject 是 android/ 这一层，仓库根是它的上一层。
val androidDir: File = rootProject.projectDir
val repoRoot: File = androidDir.parentFile

/** 从 keystore.properties 读出来的四项签名参数。 */
class ReleaseSigning(
    val keystoreFile: File,
    val storePassword: String,
    val keyAlias: String,
    val keyPassword: String,
)

/** storeFile 允许写绝对路径；写相对路径时依次相对 keystore.properties 所在目录、android/、仓库根查找。 */
fun resolveStoreFile(raw: String, propsDir: File): File {
    val direct = File(raw)
    if (direct.isAbsolute) return direct
    return listOf(
        propsDir.resolve(raw),
        androidDir.resolve(raw),
        repoRoot.resolve(raw),
    ).firstOrNull { it.isFile } ?: propsDir.resolve(raw)
}

val keystorePropsFile: File? = listOf(
    androidDir.resolve("keystore.properties"),
    repoRoot.resolve("keystore.properties"),
).firstOrNull { it.isFile }

val keystoreExampleFile: File = androidDir.resolve("keystore.properties.example")

val missingKeystoreHelp = """
    |缺少 release 签名配置，release 包打不出来（debug 包不受影响，照常能打）。
    |
    |签名密钥由你自己生成、自己保管，不放进仓库，所以构建前要先放一份 keystore.properties：
    |
    |    ${androidDir.resolve("keystore.properties")}
    |
    |放仓库根 ${repoRoot.resolve("keystore.properties")} 也认。
    |四项都要填，格式照着 $keystoreExampleFile 抄：
    |
    |    storeFile=...        # 密钥库文件路径，绝对或相对路径都行
    |    storePassword=...    # 密钥库口令
    |    keyAlias=...         # 密钥别名
    |    keyPassword=...      # 密钥口令
    |
    |还没有密钥库就先自己生成一份（只需一次，务必自己备份好）：
    |
    |    keytool -genkeypair -v -keystore release.jks -alias miaoledger \
    |      -keyalg RSA -keysize 2048 -validity 36500
    |
    |注意：签名密钥丢了，同一个 App 就再也发不出能覆盖安装的更新包。
""".trimMargin()

/** 读配置：第一个值是签名参数，第二个值非空表示缺什么（人话）。 */
fun readReleaseSigning(): Pair<ReleaseSigning?, String?> {
    val propsFile = keystorePropsFile ?: return null to missingKeystoreHelp

    val props = Properties()
    runCatching {
        // 按 UTF-8 读，并吃掉 BOM：Windows 记事本/Set-Content 存出来常带 BOM，
        // 不去掉的话第一个键会变成 "\uFEFFstoreFile"，看上去"填了"其实读不到。
        val text = propsFile.readText(Charsets.UTF_8).removePrefix("\uFEFF")
        // storeFile 这一行把 Windows 反斜杠统一成斜杠：Properties 里 "\" 是转义符，
        // 直接写 C:\keys\a.jks 会被吃成 C:keysa.jks，报错信息还对不上，容易查半天。
        val normalized = text.lineSequence().joinToString("\n") { line ->
            if (line.trimStart().startsWith("storeFile")) line.replace('\\', '/') else line
        }
        props.load(normalized.reader())
    }.onFailure {
        return null to "keystore.properties 读不出来（${it.message}）。检查文件编码和权限。\n\n$missingKeystoreHelp"
    }

    val keys = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
    val blank = keys.filter { props.getProperty(it)?.trim().isNullOrEmpty() }
    if (blank.isNotEmpty()) {
        return null to """
            |keystore.properties 里这几项还没填：${blank.joinToString("、")}
            |文件位置：$propsFile
            |
            |        现在的键：${props.stringPropertyNames().joinToString("、").takeIf { it.isNotEmpty() } ?: "（空文件）"}
            |        （占位值不能直接用，模板见 $keystoreExampleFile）
            |
            |$missingKeystoreHelp
        """.trimMargin()
    }

    val rawStore = props.getProperty("storeFile").trim()
    val storeFile = resolveStoreFile(rawStore, propsFile.parentFile)
    if (!storeFile.isFile) {
        return null to """
            |keystore.properties 里 storeFile 指向的密钥库文件不存在：
            |    storeFile = $rawStore
            |    解析成    = $storeFile
            |
            |把 jks 放到这个路径，或者把 storeFile 改对。
            |
            |$missingKeystoreHelp
        """.trimMargin()
    }

    return ReleaseSigning(
        keystoreFile = storeFile,
        storePassword = props.getProperty("storePassword").trim(),
        keyAlias = props.getProperty("keyAlias").trim(),
        keyPassword = props.getProperty("keyPassword").trim(),
    ) to null
}

val (releaseSigning, releaseSigningProblem) = readReleaseSigning()

android {
    namespace = "com.miaoledger"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.miaoledger"
        minSdk = 26
        targetSdk = 36
        versionCode = 10
        versionName = "1.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    // 不直接用默认的 ~/.android/debug.keystore：本机家目录下的 .android 目录是个链接点，
    // 某些 JDK 版本解析不了重解析点会报错。所以仓库里放一份自己的调试签名。
    // 公开仓库不带 jks，缺文件时自动回落到 AGP 默认调试签名，CI 里也能 assembleDebug。
    signingConfigs {
        getByName("debug") {
            val ks = file("../keystore/miaoledger-debug.jks")
            if (ks.exists()) {
                storeFile = ks
                storePassword = "android"
                keyAlias = "miaoledger"
                keyPassword = "android"
            }
        }
        // release 签名：能从 keystore.properties 读到才建；读不到就交给下面的检查任务报人话。
        releaseSigning?.let { rs ->
            create("release") {
                storeFile = rs.keystoreFile
                storePassword = rs.storePassword
                keyAlias = rs.keyAlias
                keyPassword = rs.keyPassword
            }
        }
    }

    // 挂到 buildTypes.release 上（写在这里是因为 signingConfigs 在 buildTypes 之后声明）
    releaseSigning?.let {
        buildTypes.getByName("release").signingConfig = signingConfigs.getByName("release")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    buildFeatures {
        compose = true
        // 版本号只在 build.gradle.kts 里写一处，界面上的「版本 x.y.z」读 BuildConfig.VERSION_NAME
        buildConfig = true
    }

    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}")
    }
}

// 签名检查放进任务里，不放配置阶段：否则 assembleDebug、gradlew tasks 都会被拦下来。
// 签名没配好时，release 相关的打包任务在动手前就停下，只输出上面那段人话。
if (releaseSigningProblem != null) {
    val problem = releaseSigningProblem
    val checkReleaseSigning = tasks.register("checkReleaseSigning") {
        group = "verification"
        description = "检查 release 签名配置（密钥由需求方提供，不进仓库）"
        doLast { throw GradleException(problem) }
    }
    tasks.matching {
        it.name.startsWith("packageRelease") ||
            it.name.startsWith("validateSigningRelease") ||
            it.name.startsWith("assembleRelease") ||
            it.name.startsWith("bundleRelease") ||
            it.name.startsWith("installRelease")
    }.configureEach { dependsOn(checkReleaseSigning) }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.activity:activity-compose:1.9.3")

    val composeBom = platform("androidx.compose:compose-bom:2025.06.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.9.0")

    // 自动备份（每 6 小时 / 启动 / 记账后补一次）；失败静默，不影响记账
    implementation("androidx.work:work-runtime-ktx:2.10.2")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.google.code.gson:gson:2.11.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
