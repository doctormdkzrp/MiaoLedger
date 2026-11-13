<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>我的账本</h2>
          <p class="sub">账本用来给账单分组，可以新建、改名、删除。</p>
        </div>
        <div class="toolbar">
          <el-button :loading="loading" @click="load">刷新</el-button>
          <el-button type="primary" @click="openCreate">新建账本</el-button>
        </div>
      </div>

      <el-table v-loading="loading" :data="books" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="图标" width="80">
          <template #default="{ row }">
            <span class="book-icon">{{ row.icon || "🏠" }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="账本名" min-width="180" />
        <el-table-column prop="sort" label="排序" width="100" />
        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">改名</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-tip">还没有账本，点右上角「新建账本」建一个吧</div>
        </template>
      </el-table>
    </div>

    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>账户与分类</h2>
          <p class="sub">这里是记账时会用到的资产账户和分类，只读展示；需要调整请在手机端操作。</p>
        </div>
      </div>

      <div class="two-col">
        <div>
          <h3 class="col-title">资产账户（{{ accounts.length }}）</h3>
          <el-tag v-for="acct in accounts" :key="acct.id" class="pill" effect="plain" type="info">
            {{ acct.name }}
          </el-tag>
          <p v-if="accounts.length === 0" class="muted">暂无账户</p>
        </div>
        <div>
          <h3 class="col-title">分类（{{ categories.length }}）</h3>
          <el-tag
            v-for="cat in categories"
            :key="cat.id"
            class="pill"
            effect="plain"
            :type="cat.kind === 'in' ? 'success' : 'warning'"
          >
            {{ cat.name }}
          </el-tag>
          <p v-if="categories.length === 0" class="muted">暂无分类</p>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '改账本名' : '新建账本'" width="420px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="76px" @submit.prevent>
        <el-form-item label="账本名" prop="name">
          <el-input v-model.trim="form.name" maxlength="32" show-word-limit placeholder="例如：日常生活" />
        </el-form-item>
        <el-form-item label="图标" prop="icon">
          <el-input v-model.trim="form.icon" maxlength="4" placeholder="例如：🏠" />
        </el-form-item>
        <el-form-item label="排序" prop="sort">
          <el-input-number v-model="form.sort" :min="0" :max="9999" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { addBook, fetchMeta, removeBook, updateBook } from "@/api/meta";
import type { Account, Book, Category } from "@/api/types";

const loading = ref(false);
const saving = ref(false);
const books = ref<Book[]>([]);
const accounts = ref<Account[]>([]);
const categories = ref<Category[]>([]);

const dialogVisible = ref(false);
const editing = ref<Book | null>(null);
const formRef = ref<FormInstance>();
const form = reactive({ name: "", icon: "🏠", sort: 0 });

const rules: FormRules = {
  name: [
    { required: true, message: "请输入账本名", trigger: "blur" },
    { min: 1, max: 32, message: "账本名最多 32 个字", trigger: "blur" }
  ]
};

async function load() {
  loading.value = true;
  try {
    const meta = await fetchMeta();
    books.value = meta.books;
    accounts.value = meta.accounts;
    categories.value = meta.categories;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  form.name = "";
  form.icon = "🏠";
  form.sort = books.value.length;
  dialogVisible.value = true;
}

function openEdit(row: Book) {
  editing.value = row;
  form.name = row.name;
  form.icon = row.icon || "🏠";
  form.sort = row.sort ?? 0;
  dialogVisible.value = true;
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
      await updateBook(editing.value.id, { name: form.name, icon: form.icon, sort: form.sort });
      ElMessage.success("改好了");
    } else {
      await addBook({ name: form.name, icon: form.icon, sort: form.sort });
      ElMessage.success("建好了");
    }
    dialogVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    saving.value = false;
  }
}

async function onDelete(row: Book) {
  try {
    await ElMessageBox.confirm(
      `删除「${row.name}」后，这个账本下的账单不会一起删掉。确定删除吗？`,
      "删除账本",
      { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await removeBook(row.id);
    ElMessage.success("删掉了");
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败了");
  }
}

onMounted(load);
</script>

<style scoped>
.book-icon {
  font-size: 18px;
}

.two-col {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 24px;
}

.col-title {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--miao-text);
}

.pill {
  margin: 0 8px 8px 0;
}
</style>
