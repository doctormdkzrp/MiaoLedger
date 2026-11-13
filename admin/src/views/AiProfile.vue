<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>我的 AI 提示词</h2>
          <p class="sub">
            这些是给手机端 AI 记账用的偏好说明，比如「奶茶算零食」「工资走银行卡」。
          </p>
        </div>
        <div class="toolbar">
          <el-button :loading="loading" @click="load">重新读取</el-button>
          <el-button type="primary" :loading="saving" :disabled="!dirty" @click="save">保存</el-button>
        </div>
      </div>

      <el-skeleton v-if="loading && !loadedOnce" :rows="6" animated />

      <template v-else>
        <el-input
          v-model="hints"
          type="textarea"
          :rows="10"
          :maxlength="HINTS_LIMIT"
          show-word-limit
          resize="vertical"
          placeholder="例如：外卖算餐饮、奶茶算零食；工资进银行卡；每月 1 号交房租。"
        />

        <div class="meta-row">
          <span class="count" :class="{ over: hints.length > HINTS_LIMIT }">
            已写 {{ hints.length }} / {{ HINTS_LIMIT }} 字
          </span>
          <span class="muted">版本 v{{ profile?.version ?? 0 }}</span>
          <span class="muted">学习反馈 {{ profile?.feedback_count ?? 0 }} 条</span>
          <span class="muted">最后更新 {{ profile?.updated_at ? datetime(profile.updated_at) : "还没保存过" }}</span>
        </div>

        <p class="muted tip">
          提示：写得越具体，手机端识别分类越准。清空后保存就等于把提示词删掉。
        </p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { HINTS_LIMIT, fetchProfile, saveProfile } from "@/api/ai";
import type { AiProfile } from "@/api/types";
import { datetime } from "@/utils/format";

const loading = ref(false);
const saving = ref(false);
const loadedOnce = ref(false);
const profile = ref<AiProfile | null>(null);
const hints = ref("");
const original = ref("");

const dirty = computed(() => hints.value !== original.value);

async function load() {
  loading.value = true;
  try {
    const data = await fetchProfile();
    profile.value = data;
    hints.value = data.hints ?? "";
    original.value = hints.value;
    loadedOnce.value = true;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "读取失败了");
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (hints.value.length > HINTS_LIMIT) {
    ElMessage.warning(`提示词最多 ${HINTS_LIMIT} 字，现在 ${hints.value.length} 字`);
    return;
  }
  saving.value = true;
  try {
    const data = await saveProfile(hints.value);
    profile.value = data;
    hints.value = data.hints ?? "";
    original.value = hints.value;
    ElMessage.success("保存好了");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.meta-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 12px;
}

.count {
  font-size: 13px;
  color: var(--miao-text-sub);
}

.count.over {
  color: #d64545;
  font-weight: 600;
}

.tip {
  margin: 14px 0 0;
}
</style>
