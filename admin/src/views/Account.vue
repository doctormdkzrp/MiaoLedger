<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>我的账号</h2>
          <p class="sub">这里看到的是当前登录的账号信息，密码可以在这里改。</p>
        </div>
        <el-button :loading="loadingMe" @click="loadMe">刷新</el-button>
      </div>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="账号">{{ me?.username || userStore.user?.username || "-" }}</el-descriptions-item>
        <el-descriptions-item label="昵称">
          {{ me?.display_name || userStore.user?.display_name || "-" }}
        </el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="me?.role === 'admin' ? 'warning' : 'info'" size="small" effect="plain">
            {{ roleLabel(me?.role || userStore.user?.role || "user") }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="账单条数">{{ me?.txns ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="账本 / 账户 / 分类">
          {{ me?.books ?? 0 }} / {{ me?.accounts ?? 0 }} / {{ me?.categories ?? 0 }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>改密码</h2>
          <p class="sub">
            密码是 6 位数字。改完之后，其它设备需要重新登录，当前这台不受影响。
          </p>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="96px"
        class="pin-form"
        @submit.prevent
      >
        <el-form-item label="现在的密码" prop="oldPin">
          <el-input v-model.trim="form.oldPin" type="password" show-password maxlength="32" placeholder="6 位数字" />
        </el-form-item>
        <el-form-item label="新密码" prop="newPin">
          <el-input v-model.trim="form.newPin" type="password" show-password maxlength="32" placeholder="6 位数字" />
        </el-form-item>
        <el-form-item label="再输一次" prop="confirmPin">
          <el-input v-model.trim="form.confirmPin" type="password" show-password maxlength="32" placeholder="再输一次新密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="submit">保存新密码</el-button>
          <el-button @click="resetForm">清空</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { fetchMe } from "@/api/meta";
import { changePin } from "@/api/auth";
import type { MeOut } from "@/api/types";
import { useUserStore } from "@/stores";
import { roleLabel } from "@/utils/format";

const userStore = useUserStore();

const me = ref<MeOut | null>(null);
const loadingMe = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();

const form = reactive({ oldPin: "", newPin: "", confirmPin: "" });

const rules: FormRules = {
  oldPin: [
    { required: true, message: "请输入现在的密码", trigger: "blur" },
    { pattern: /^\d{4,32}$/, message: "密码由数字组成", trigger: "blur" }
  ],
  newPin: [
    { required: true, message: "请输入新密码", trigger: "blur" },
    { pattern: /^\d{6}$/, message: "新密码要正好 6 位数字", trigger: "blur" }
  ],
  confirmPin: [
    { required: true, message: "请再输一次新密码", trigger: "blur" },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== form.newPin) callback(new Error("两次输入的新密码不一样"));
        else callback();
      },
      trigger: "blur"
    }
  ]
};

async function loadMe() {
  loadingMe.value = true;
  try {
    me.value = await fetchMe();
    if (me.value) {
      userStore.patchUser({
        username: me.value.username,
        display_name: me.value.display_name,
        role: me.value.role
      });
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载失败了");
  } finally {
    loadingMe.value = false;
  }
}

function resetForm() {
  form.oldPin = "";
  form.newPin = "";
  form.confirmPin = "";
  formRef.value?.clearValidate();
}

async function submit() {
  const formEl = formRef.value;
  if (formEl) {
    const ok = await formEl.validate().catch(() => false);
    if (!ok) return;
  }

  try {
    await ElMessageBox.confirm("改完之后其它设备要重新登录，确定改吗？", "改密码", {
      confirmButtonText: "确定改",
      cancelButtonText: "取消",
      type: "warning"
    });
  } catch {
    return;
  }

  saving.value = true;
  try {
    const res = await changePin({ old_pin: form.oldPin, new_pin: form.newPin });
    const revoked = res.revoked_devices ?? 0;
    ElMessage.success(revoked > 0 ? `改好了，另外 ${revoked} 台设备被踢下线` : "改好了");
    resetForm();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "改密码失败了");
  } finally {
    saving.value = false;
  }
}

onMounted(loadMe);
</script>

<style scoped>
.pin-form {
  max-width: 460px;
}
</style>
