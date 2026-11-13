<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>用户管理</h2>
          <p class="sub">
            管理这台服务上的所有账号：建号、改昵称和角色、重置密码，以及查看/代记某个用户的账单。
          </p>
        </div>
        <div class="toolbar">
          <el-input
            v-model.trim="keyword"
            placeholder="搜账号或昵称"
            clearable
            style="width: 200px"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button :loading="loading" @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新建用户</el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="filtered" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="账号" min-width="130" />
        <el-table-column label="昵称" min-width="130">
          <template #default="{ row }">{{ row.display_name || "-" }}</template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'warning' : 'info'" size="small" effect="plain">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="txns" label="账单数" width="100" align="right" />
        <el-table-column prop="books" label="账本数" width="100" align="right" />
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ datetime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="openCreate(row)">复制建号</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-tip">还没有用户</div>
        </template>
      </el-table>

      <p class="muted note">
        提示：改密码会让该用户的所有设备下线；降级最后一个管理员会被后端拒绝。
      </p>
    </div>

    <!-- 新建 / 编辑用户 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="440px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="76px" @submit.prevent>
        <el-form-item label="账号名" prop="username">
          <el-input v-model.trim="form.username" maxlength="20" show-word-limit placeholder="2–20 位字母、数字或下划线" />
        </el-form-item>
        <el-form-item label="昵称" prop="displayName">
          <el-input v-model.trim="form.displayName" maxlength="20" show-word-limit placeholder="显示给用户看的名字" />
        </el-form-item>
        <el-form-item :label="editing ? '重置密码' : '初始密码'" prop="pin">
          <el-input v-model.trim="form.pin" maxlength="32" placeholder="6 位数字" />
          <div v-if="editing" class="muted form-tip">留空表示不改密码</div>
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-radio-group v-model="form.role">
            <el-radio-button value="user">普通用户</el-radio-button>
            <el-radio-button value="admin">管理员</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <UserDetail v-model="detailVisible" :user="activeUser" @changed="load" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { Search } from "@element-plus/icons-vue";
import { createUser, fetchUsers, updateUser } from "@/api/admin";
import type { AdminUser, Role } from "@/api/types";
import { datetime, roleLabel } from "@/utils/format";
import UserDetail from "./UserDetail.vue";

const loading = ref(false);
const saving = ref(false);
const users = ref<AdminUser[]>([]);
const keyword = ref("");

const dialogVisible = ref(false);
const editing = ref<AdminUser | null>(null);
const formRef = ref<FormInstance>();
const form = reactive({
  username: "",
  displayName: "",
  pin: "",
  role: "user" as Role
});

const detailVisible = ref(false);
const activeUser = ref<AdminUser | null>(null);

const dialogTitle = computed(() => (editing.value ? `编辑用户：${editing.value.username}` : "新建用户"));

const filtered = computed(() => {
  const key = keyword.value.toLowerCase();
  if (!key) return users.value;
  return users.value.filter(
    user =>
      user.username.toLowerCase().includes(key) ||
      (user.display_name || "").toLowerCase().includes(key)
  );
});

const rules: FormRules = {
  username: [
    { required: true, message: "请输入账号名", trigger: "blur" },
    {
      pattern: /^[A-Za-z0-9_]{2,20}$/,
      message: "账号名只能用 2–20 位英文字母、数字或下划线",
      trigger: "blur"
    }
  ],
  displayName: [{ max: 20, message: "昵称最多 20 个字", trigger: "blur" }],
  pin: [
    {
      validator: (_rule, value: string, callback) => {
        if (editing.value && !value) {
          callback();
          return;
        }
        if (!value) {
          callback(new Error("请设置初始密码"));
          return;
        }
        if (!/^\d{6}$/.test(value)) {
          callback(new Error("密码要 6 位数字"));
          return;
        }
        callback();
      },
      trigger: "blur"
    }
  ]
};

async function load() {
  loading.value = true;
  try {
    users.value = await fetchUsers();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "用户列表加载失败了");
  } finally {
    loading.value = false;
  }
}

function openCreate(source?: AdminUser) {
  editing.value = null;
  form.username = source ? `${source.username}_2` : "";
  form.displayName = source ? `${source.display_name || source.username}（副本）` : "";
  form.pin = "";
  form.role = "user";
  dialogVisible.value = true;
  formRef.value?.clearValidate();
}

function openEdit(row: AdminUser) {
  editing.value = row;
  form.username = row.username;
  form.displayName = row.display_name || "";
  form.pin = "";
  form.role = row.role;
  dialogVisible.value = true;
  formRef.value?.clearValidate();
}

function openDetail(row: AdminUser) {
  activeUser.value = row;
  detailVisible.value = true;
}

async function save() {
  const formEl = formRef.value;
  if (formEl) {
    const ok = await formEl.validate().catch(() => false);
    if (!ok) return;
  }

  saving.value = true;
  try {
    if (editing.value) {
      const payload: Record<string, unknown> = {
        username: form.username,
        display_name: form.displayName,
        role: form.role
      };
      if (form.pin) payload.pin = form.pin;

      if (editing.value.role === "admin" && form.role !== "admin") {
        try {
          await ElMessageBox.confirm(
            "把管理员改成普通用户后，他就看不到用户管理了。确定吗？",
            "改角色",
            { confirmButtonText: "确定", cancelButtonText: "取消", type: "warning" }
          );
        } catch {
          saving.value = false;
          return;
        }
      }

      const res = await updateUser(editing.value.id, payload);
      ElMessage.success(
        res.revoked_devices > 0 ? `改好了，该用户 ${res.revoked_devices} 台设备被踢下线` : "改好了"
      );
    } else {
      await createUser({
        username: form.username,
        pin: form.pin,
        display_name: form.displayName,
        role: form.role
      });
      ElMessage.success("用户建好了");
    }
    dialogVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.note {
  margin: 14px 0 0;
}

.form-tip {
  margin-top: 2px;
}
</style>
