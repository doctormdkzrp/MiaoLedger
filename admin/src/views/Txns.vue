<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>我的账单</h2>
          <p class="sub">按月份看支出、收入和结余；每一笔都能改金额、分类、时间或备注。</p>
        </div>
        <div class="toolbar">
          <el-date-picker
            v-model="month"
            type="month"
            value-format="YYYY-MM"
            :clearable="false"
            placeholder="选月份"
            style="width: 140px"
            @change="load"
          />
          <el-select v-model="bookId" placeholder="全部账本" clearable style="width: 150px" @change="load">
            <el-option v-for="book in books" :key="book.id" :label="book.name" :value="book.id" />
          </el-select>
          <el-button :loading="loading" @click="load">刷新</el-button>
        </div>
      </div>

      <div class="stat-grid">
        <div class="stat out">
          <div class="label">本月支出</div>
          <div class="value">{{ yuan(summary?.out_cents) }} 元</div>
        </div>
        <div class="stat in">
          <div class="label">本月收入</div>
          <div class="value">{{ yuan(summary?.in_cents) }} 元</div>
        </div>
        <div class="stat left">
          <div class="label">本月结余</div>
          <div class="value">{{ yuan(summary?.left_cents) }} 元</div>
        </div>
        <div class="stat">
          <div class="label">笔数</div>
          <div class="value">{{ summary?.count ?? 0 }}</div>
        </div>
      </div>

      <div v-if="topCategories.length" class="cat-row">
        <span class="muted">支出分类占比：</span>
        <el-tag v-for="cat in topCategories" :key="cat.name" class="pill" type="warning" effect="plain">
          {{ cat.name }} {{ yuan(cat.cents) }} 元
        </el-tag>
      </div>
    </div>

    <div class="page-card">
      <div class="page-head">
        <h2>账单明细（{{ rows.length }} 笔）</h2>
      </div>

      <el-table v-loading="loading" :data="rows" stripe style="width: 100%">
        <el-table-column prop="occurred_at" label="时间" width="160">
          <template #default="{ row }">{{ datetime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column label="收支" width="84">
          <template #default="{ row }">
            <el-tag size="small" :type="kindTagType(row.kind)" effect="light">
              {{ kindLabel(row.kind) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="120" align="right">
          <template #default="{ row }">
            <span class="money" :class="row.kind === 'in' ? 'money-in' : 'money-out'">
              {{ row.kind === "in" ? "+" : "-" }}{{ yuan(row.amount_cents) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="130">
          <template #default="{ row }">{{ catName(row.cat_id) }}</template>
        </el-table-column>
        <el-table-column label="账户" width="130">
          <template #default="{ row }">{{ accountName(row.account_id) }}</template>
        </el-table-column>
        <el-table-column label="账本" width="130">
          <template #default="{ row }">{{ bookName(row.book_id) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="130" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-tip">这个月还没有账单，去手机端记一笔吧</div>
        </template>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="编辑账单" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="76px" @submit.prevent>
        <el-form-item label="收支" prop="kind">
          <el-radio-group v-model="form.kind">
            <el-radio-button value="out">支出</el-radio-button>
            <el-radio-button value="in">收入</el-radio-button>
            <el-radio-button value="transfer">转账</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input v-model.trim="form.amount" placeholder="例如 25.80">
            <template #append>元</template>
          </el-input>
        </el-form-item>
        <el-form-item label="时间" prop="occurredAt">
          <el-date-picker
            v-model="form.occurredAt"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="选时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.catId" placeholder="不指定" clearable style="width: 100%">
            <el-option
              v-for="cat in filteredCategories"
              :key="cat.id"
              :label="cat.name"
              :value="cat.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="账户">
          <el-select v-model="form.accountId" placeholder="不指定" clearable style="width: 100%">
            <el-option v-for="acct in accounts" :key="acct.id" :label="acct.name" :value="acct.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="账本">
          <el-select v-model="form.bookId" placeholder="不指定" clearable style="width: 100%">
            <el-option v-for="book in books" :key="book.id" :label="book.name" :value="book.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注" prop="note">
          <el-input v-model.trim="form.note" type="textarea" :rows="2" maxlength="200" show-word-limit />
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
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { fetchMeta } from "@/api/meta";
import { patchTxn, removeTxn, fetchTxns } from "@/api/txns";
import { fetchSummary } from "@/api/summary";
import type { Account, Book, Category, SummaryOut, Txn, TxnKind } from "@/api/types";
import { currentMonth, datetime, kindLabel, kindTagType, toCents, yuan } from "@/utils/format";

const loading = ref(false);
const saving = ref(false);
const month = ref(currentMonth());
const bookId = ref<number | null>(null);

const rows = ref<Txn[]>([]);
const summary = ref<SummaryOut | null>(null);
const books = ref<Book[]>([]);
const accounts = ref<Account[]>([]);
const categories = ref<Category[]>([]);

const dialogVisible = ref(false);
const editing = ref<Txn | null>(null);
const formRef = ref<FormInstance>();
const form = reactive({
  kind: "out" as TxnKind,
  amount: "",
  occurredAt: "",
  catId: null as number | null,
  accountId: null as number | null,
  bookId: null as number | null,
  note: ""
});

const topCategories = computed(() => (summary.value?.by_category ?? []).slice(0, 6));

const filteredCategories = computed(() =>
  categories.value.filter(cat => cat.kind === form.kind || cat.kind === "transfer")
);

const rules: FormRules = {
  amount: [
    { required: true, message: "请输入金额", trigger: "blur" },
    {
      validator: (_rule, value: string, callback) => {
        const cents = toCents(value);
        if (Number.isNaN(cents)) callback(new Error("金额要是数字，最多两位小数"));
        else if (cents <= 0) callback(new Error("金额要大于 0"));
        else callback();
      },
      trigger: "blur"
    }
  ],
  occurredAt: [{ required: true, message: "请选择时间", trigger: "change" }]
};

function catName(id: number | null): string {
  if (id == null) return "-";
  return categories.value.find(c => c.id === id)?.name ?? `#${id}`;
}

function accountName(id: number | null): string {
  if (id == null) return "-";
  return accounts.value.find(a => a.id === id)?.name ?? `#${id}`;
}

function bookName(id: number | null): string {
  if (id == null) return "-";
  return books.value.find(b => b.id === id)?.name ?? `#${id}`;
}

function monthPrefix(): string {
  return month.value;
}

async function load() {
  loading.value = true;
  try {
    const [meta, list, sum] = await Promise.all([
      fetchMeta(),
      fetchTxns({ book_id: bookId.value, include_deleted: false }),
      fetchSummary(month.value, bookId.value)
    ]);
    books.value = meta.books;
    accounts.value = meta.accounts;
    categories.value = meta.categories;
    summary.value = sum;
    rows.value = list.filter(row => row.occurred_at.startsWith(monthPrefix()));
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载失败了");
  } finally {
    loading.value = false;
  }
}

function openEdit(row: Txn) {
  editing.value = row;
  form.kind = row.kind;
  form.amount = yuan(row.amount_cents);
  form.occurredAt = row.occurred_at.slice(0, 19);
  form.catId = row.cat_id;
  form.accountId = row.account_id;
  form.bookId = row.book_id;
  form.note = row.note ?? "";
  dialogVisible.value = true;
}

async function save() {
  const formEl = formRef.value;
  if (formEl) {
    const ok = await formEl.validate().catch(() => false);
    if (!ok) return;
  }
  if (!editing.value) return;

  const cents = toCents(form.amount);
  saving.value = true;
  try {
    await patchTxn(editing.value.client_uuid, {
      kind: form.kind,
      amount_cents: cents,
      occurred_at: form.occurredAt,
      cat_id: form.catId,
      account_id: form.accountId,
      book_id: form.bookId,
      note: form.note
    });
    ElMessage.success("改好了");
    dialogVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    saving.value = false;
  }
}

async function onDelete(row: Txn) {
  try {
    await ElMessageBox.confirm("删除后这笔账在手机端也会消失，确定删除吗？", "删除账单", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning"
    });
  } catch {
    return;
  }
  try {
    await removeTxn(row.client_uuid);
    ElMessage.success("删掉了");
    await load();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败了");
  }
}

onMounted(load);
</script>

<style scoped>
.cat-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.pill {
  margin-right: 0;
}
</style>
