# release 开 minify + shrinkResources 时用的规则。debug 包不走这里。
#
# Compose / AndroidX / OkHttp 都自带 consumer rules，一般不用手写。
# 需要手写的只有反射：Gson 按字段名序列化，混淆后字段名一变，本地缓存和接口返回就全对不上。

# 数据类（Txn / Book / Cat / Acct / AiRule ...）整体保留：字段名是 Gson 的契约，
# 少了任何一条就会出现「数据变成 null」「界面显示连不上服务器」这类问题。
-keep class com.miaoledger.data.** { *; }

# Gson 反射本身（TypeToken 拿泛型、字段名映射）
-keepattributes Signature
-keepattributes *Annotation*
-keepattributes InnerClasses,EnclosingMethod
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken

# 枚举：values()/valueOf() 被 R8 裁掉会运行时报错
-keepclassmembers enum * {
    public static **[] values();
    public static ** valueOf(java.lang.String);
}

# 自定义 View / Activity 由 Manifest 反射创建，名字不能改
-keep public class * extends android.app.Activity
