plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.miaoledger"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.miaoledger"
        minSdk = 26
        targetSdk = 36
        versionCode = 10
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
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
