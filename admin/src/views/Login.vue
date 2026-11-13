<template>
  <div class="login-page">
    <div class="login-card">
      <div class="brand">
        <MiaoLogo :size="46" class="logo" />
        <div>
          <h1>小喵记账</h1>
          <p>管理台 · 用账号和 6 位数字密码登录</p>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="账号" prop="username">
          <el-input
            v-model.trim="form.username"
            placeholder="请输入账号名"
            size="large"
            autocomplete="username"
            maxlength="32"
            @keyup.enter="submit"
          >
            <template #prefix>
              <el-icon><User /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="密码（6 位数字）" prop="pin">
          <el-input
            v-model.trim="form.pin"
            type="password"
            placeholder="请输入 6 位数字密码"
            size="large"
            show-password
            autocomplete="current-password"
            maxlength="32"
            @keyup.enter="submit"
          >
            <template #prefix>
              <el-icon><Lock /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>

      <p v-if="errorText" class="error">{{ errorText }}</p>

      <p class="tip">手机上注册的账号可以直接在这里登录；忘记密码请用手机端重置。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { Lock, User } from "@element-plus/icons-vue";
import type { FormInstance, FormRules } from "element-plus";
import MiaoLogo from "@/components/MiaoLogo.vue";
import { useUserStore } from "@/stores";

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();

const formRef = ref<FormInstance>();
const loading = ref(false);
const errorText = ref("");

const form = reactive({
  username: "",
  pin: ""
});

const rules: FormRules = {
  username: [
    { required: true, message: "请输入账号", trigger: "blur" },
    { min: 2, max: 32, message: "账号长度 2–32 位", trigger: "blur" }
  ],
  pin: [
    { required: true, message: "请输入密码", trigger: "blur" },
    { pattern: /^\d{4,32}$/, message: "密码是数字（注册的账号为 6 位）", trigger: "blur" }
  ]
};

async function submit() {
  if (loading.value) return;
  errorText.value = "";

  const formEl = formRef.value;
  if (formEl) {
    const ok = await formEl.validate().catch(() => false);
    if (!ok) return;
  }

  loading.value = true;
  try {
    const data = await userStore.login({ username: form.username, pin: form.pin });
    ElMessage.success(`欢迎回来，${data.display_name || data.username}`);
    const redirect = route.query.redirect;
    const target = typeof redirect === "string" && redirect.startsWith("/") ? redirect : "/books";
    router.replace(target);
  } catch (error) {
    errorText.value = error instanceof Error ? error.message : "登录失败了";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background:
    radial-gradient(1200px 600px at 10% 0%, #d9ecfc 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 100%, #e8f3fd 0%, transparent 50%),
    #f2f5f9;
}

.login-card {
  width: 100%;
  max-width: 380px;
  padding: 32px 30px 26px;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 20px 50px -24px rgba(16, 24, 40, 0.3), 0 2px 6px rgba(16, 24, 40, 0.05);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}

.logo {
  border-radius: 14px;
  overflow: hidden;
}

.brand h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.brand p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--miao-text-sub);
}

.submit {
  width: 100%;
  margin-top: 6px;
  letter-spacing: 4px;
}

.error {
  margin: 14px 0 0;
  font-size: 13px;
  color: #d64545;
}

.tip {
  margin: 18px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: #9aa2af;
}
</style>
