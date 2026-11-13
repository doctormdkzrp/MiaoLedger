<template>
  <el-drawer
    :model-value="modelValue"
    :title="user ? `用户：${user.display_name || user.username}` : '用户详情'"
    size="980px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <div v-if="user" class="detail">
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="账号">{{ user.username }}</el-descriptions-item>
        <el-descriptions-item label="昵称">{{ user.display_name || "-" }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="user.role === 'admin' ? 'warning' : 'info'" size="small" effect="plain">
            {{ roleLabel(user.role) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="账单条数">{{ user.txns }}</el-descriptions-item>
        <el-descriptions-item label="账本数">{{ user.books }}</el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ datetime(user.created_at) }}</el-descriptions-item>
      </el-descriptions>

      <el-tabs v-model="tab" class="tabs">
        <!-- ---------------- 账单 ---------------- -->
        <el-tab-pane label="账单" name="txns">
          <div class="filters">
            <el-date-picker
              v-model="range"
              type="daterange"
              value-format="YYYY-MM-DD"
              range-separator="到"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              style="width: 260px"
              @change="loadTxns(1)"
            />
            <el-select
              v-model="filterBook"
              placeholder="全部账本"
              clearable
              style="width: 150px"
              @change="loadTxns(1)"
            >
              <el-option v-for="book in books" :key="book.id" :label="book.name" :value="book.id" />
            </el-select>
            <el-checkbox v-model="includeDeleted" @change="loadTxns(1)">含已删除</el-checkbox>
            <span class="grow" />
            <el-button type="primary" @click="openCreateTxn">代记一笔</el-button>
            <el-button :loading="txnLoading" @click="loadTxns(page)">刷新</el-button>
          </div>

          <el-table v-loading="txnLoading" :data="txns" size="small" stripe style="width: 100%">
            <el-table-column label="时间" width="140">
              <template #default="{ row }">{{ datetime(row.occurred_at) }}</template>
            </el-table-column>
            <el-table-column label="收支" width="76">
              <template #default="{ row }">
                <el-tag size="small" :type="kindTagType(row.kind)" effect="light">
                  {{ kindLabel(row.kind) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="110" align="right">
              <template #default="{ row }">
                <span class="money" :class="row.kind === 'in' ? 'money-in' : 'money-out'">
                  {{ row.kind === "in" ? "+" : "-" }}{{ yuan(row.amount_cents) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="110">
              <template #default="{ row }">{{ catName(row.cat_id) }}</template>
            </el-table-column>
            <el-table-column label="账本" width="110">
              <template #default="{ row }">{{ bookName(row.book_id) }}</template>
            </el-table-column>
            <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.deleted" size="small" type="info">已删</el-tag>
                <span v-else class="muted">正常</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEditTxn(row)">编辑</el-button>
                <el-button link type="danger" :disabled="row.deleted" @click="onDeleteTxn(row)">删除</el-button>
              </template>
            </el-table-column>
            <template #empty>
              <div class="empty-tip">这个用户还没有账单</div>
            </template>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="page"
              :page-size="pageSize"
              :total="total"
              layout="total, prev, pager, next"
              background
              @current-change="(p: number) => loadTxns(p)"
            />
          </div>
        </el-tab-pane>

        <!-- ---------------- AI 提示词 ---------------- -->
        <el-tab-pane label="AI 提示词" name="ai">
          <el-skeleton v-if="profileLoading" :rows="5" animated />
          <template v-else>
            <el-input
              v-model="hints"
              type="textarea"
              :rows="9"
              :maxlength="HINTS_LIMIT"
              show-word-limit
              resize="vertical"
              placeholder="这个用户的 AI 记账偏好说明"
            />
            <div class="filters" style="margin-top: 12px">
              <span class="muted">已写 {{ hints.length }} / {{ HINTS_LIMIT }} 字</span>
              <span class="muted">版本 v{{ profile?.version ?? 0 }}</span>
              <span class="muted">反馈 {{ profile?.feedback_count ?? 0 }} 条</span>
              <span class="grow" />
              <el-button type="primary" :loading="profileSaving" @click="saveProfileHints">保存提示词</el-button>
            </div>
          </template>
        </el-tab-pane>

        <!-- ---------------- 导入导出 ---------------- -->
        <el-tab-pane label="导入导出" name="io">
          <div class="io-block">
            <h4>导出账本</h4>
            <p class="muted">8 列 CSV，时间范围必填。</p>
            <div class="filters">
              <el-date-picker
                v-model="exportRange"
                type="daterange"
                value-format="YYYY-MM-DD"
                range-separator="到"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                :clearable="false"
              />
              <el-button type="primary" :loading="exporting" @click="onExport">导出 CSV</el-button>
            </div>
          </div>

          <el-divider />

          <div class="io-block">
            <h4>导入账单</h4>
            <p class="muted">选 8 列 CSV 文件；账本、分类、账户按名字自动补齐，重复行跳过。</p>
            <div class="filters">
              <el-upload
                :auto-upload="false"
                :limit="1"
                accept=".csv,text/csv"
                :on-change="onFilePicked"
                :on-remove="() => (importFile = null)"
              >
                <el-button plain>选择 CSV 文件</el-button>
              </el-upload>
              <el-button type="primary" :disabled="!importFile" :loading="importing" @click="onImport">
                开始导入
              </el-button>
            </div>
            <div v-if="importResult" style="margin-top: 10px">
              <el-tag type="success" effect="dark">成功 {{ importResult.imported }} 条</el-tag>
              <el-tag v-if="importResult.skipped" type="info" class="gap">跳过 {{ importResult.skipped }} 条</el-tag>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 代记 / 编辑账单 -->
    <el-dialog v-model="txnDialog" :title="editingTxn ? '修改这笔账' : '代记一笔'" width="460px" append-to-body>
      <el-form ref="txnFormRef" :model="txnForm" :rules="txnRules" label-width="76px" @submit.prevent>
        <el-form-item label="收支" prop="kind">
          <el-radio-group v-model="txnForm.kind">
            <el-radio-button value="out">支出</el-radio-button>
            <el-radio-button value="in">收入</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="金额" prop="amount">
          <el-input v-model.trim="txnForm.amount" placeholder="例如 25.80">
            <template #append>元</template>
          </el-input>
        </el-form-item>
        <el-form-item label="时间" prop="occurredAt">
          <el-date-picker
            v-model="txnForm.occurredAt"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="选时间"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="账本">
          <el-select v-model="txnForm.bookId" placeholder="默认账本" clearable style="width: 100%">
            <el-option v-for="book in books" :key="book.id" :label="book.name" :value="book.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="txnForm.catId" placeholder="不指定" clearable style="width: 100%">
            <el-option v-for="cat in categories" :key="cat.id" :label="cat.name" :value="cat.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model.trim="txnForm.note" type="textarea" :rows="2" maxlength="200" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="txnDialog = false">取消</el-button>
        <el-button type="primary" :loading="txnSaving" @click="saveTxn">保存</el-button>
      </template>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage, ElMessageBox } from "element-plus";
import type { FormInstance, FormRules, UploadFile } from "element-plus";
import {
  createUserTxn,
  exportUserCsv,
  fetchUserMeta,
  fetchUserProfile,
  fetchUserTxns,
  importUserCsv,
  patchUserTxn,
  removeUserTxn,
  saveUserProfile
} from "@/api/admin";
import { HINTS_LIMIT } from "@/api/ai";
import type {
  Account,
  AdminUser,
  AiProfile,
  Book,
  Category,
  ImportResult,
  Txn,
  TxnKind
} from "@/api/types";
import { datetime, kindLabel, kindTagType, monthRange, roleLabel, toCents, yuan } from "@/utils/format";

const props = defineProps<{ modelValue: boolean; user: AdminUser | null }>();
const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "changed"): void;
}>();

const tab = ref("txns");

/** ---------------- 元数据 ---------------- */
const books = ref<Book[]>([]);
const categories = ref<Category[]>([]);
const accounts = ref<Account[]>([]);

function catName(id: number | null): string {
  if (id == null) return "-";
  return categories.value.find(c => c.id === id)?.name ?? `#${id}`;
}

function bookName(id: number | null): string {
  if (id == null) return "-";
  return books.value.find(b => b.id === id)?.name ?? `#${id}`;
}

async function loadMeta() {
  if (!props.user) return;
  try {
    const meta = await fetchUserMeta(props.user.id);
    books.value = meta.books;
    categories.value = meta.categories;
    accounts.value = meta.accounts;
  } catch {
    // 元数据拉不到时页面上降级显示 id
  }
}

/** ---------------- 账单列表 ---------------- */
const txns = ref<Txn[]>([]);
const txnLoading = ref(false);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const range = ref<[string, string] | null>(null);
const filterBook = ref<number | null>(null);
const includeDeleted = ref(false);

function buildQuery() {
  const query: Record<string, unknown> = {
    limit: pageSize,
    offset: (page.value - 1) * pageSize,
    include_deleted: includeDeleted.value
  };
  if (filterBook.value != null) query.book_id = filterBook.value;
  if (range.value && range.value.length === 2) {
    query.from = range.value[0];
    query.to = range.value[1];
  }
  return query;
}

async function loadTxns(target = 1) {
  if (!props.user) return;
  page.value = target;
  txnLoading.value = true;
  try {
    const res = await fetchUserTxns(props.user.id, buildQuery());
    txns.value = res.items;
    total.value = res.total;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "账单加载失败了");
  } finally {
    txnLoading.value = false;
  }
}

/** ---------------- 代记 / 编辑账单 ---------------- */
const txnDialog = ref(false);
const txnSaving = ref(false);
const editingTxn = ref<Txn | null>(null);
const txnFormRef = ref<FormInstance>();
const txnForm = reactive({
  kind: "out" as TxnKind,
  amount: "",
  occurredAt: "",
  bookId: null as number | null,
  catId: null as number | null,
  note: ""
});

const txnRules: FormRules = {
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

function openCreateTxn() {
  editingTxn.value = null;
  txnForm.kind = "out";
  txnForm.amount = "";
  txnForm.occurredAt = dayjs().format("YYYY-MM-DDTHH:mm:ss");
  txnForm.bookId = books.value[0]?.id ?? null;
  txnForm.catId = null;
  txnForm.note = "";
  txnDialog.value = true;
}

function openEditTxn(row: Txn) {
  editingTxn.value = row;
  txnForm.kind = row.kind;
  txnForm.amount = yuan(row.amount_cents);
  txnForm.occurredAt = row.occurred_at.slice(0, 19);
  txnForm.bookId = row.book_id;
  txnForm.catId = row.cat_id;
  txnForm.note = row.note ?? "";
  txnDialog.value = true;
}

async function saveTxn() {
  if (!props.user) return;
  const formEl = txnFormRef.value;
  if (formEl) {
    const ok = await formEl.validate().catch(() => false);
    if (!ok) return;
  }
  const cents = toCents(txnForm.amount);
  txnSaving.value = true;
  try {
    if (editingTxn.value) {
      await patchUserTxn(props.user.id, editingTxn.value.client_uuid, {
        kind: txnForm.kind,
        amount_cents: cents,
        occurred_at: txnForm.occurredAt,
        book_id: txnForm.bookId,
        cat_id: txnForm.catId,
        note: txnForm.note
      });
      ElMessage.success("改好了");
    } else {
      await createUserTxn(props.user.id, {
        kind: txnForm.kind,
        amount_cents: cents,
        occurred_at: txnForm.occurredAt,
        book_id: txnForm.bookId,
        cat_id: txnForm.catId,
        note: txnForm.note
      });
      ElMessage.success("记好了");
    }
    txnDialog.value = false;
    await loadTxns(editingTxn.value ? page.value : 1);
    emit("changed");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    txnSaving.value = false;
  }
}

async function onDeleteTxn(row: Txn) {
  if (!props.user) return;
  try {
    await ElMessageBox.confirm("删除后该用户在手机端也看不到这笔账，确定吗？", "删除账单", {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning"
    });
  } catch {
    return;
  }
  try {
    await removeUserTxn(props.user.id, row.client_uuid);
    ElMessage.success("删掉了");
    await loadTxns(page.value);
    emit("changed");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "删除失败了");
  }
}

/** ---------------- AI 提示词 ---------------- */
const profile = ref<AiProfile | null>(null);
const hints = ref("");
const profileLoading = ref(false);
const profileSaving = ref(false);

async function loadProfile() {
  if (!props.user) return;
  profileLoading.value = true;
  try {
    const data = await fetchUserProfile(props.user.id);
    profile.value = data;
    hints.value = data.hints ?? "";
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "提示词读取失败了");
  } finally {
    profileLoading.value = false;
  }
}

async function saveProfileHints() {
  if (!props.user) return;
  if (hints.value.length > HINTS_LIMIT) {
    ElMessage.warning(`提示词最多 ${HINTS_LIMIT} 字`);
    return;
  }
  profileSaving.value = true;
  try {
    const data = await saveUserProfile(props.user.id, hints.value);
    profile.value = data;
    hints.value = data.hints ?? "";
    ElMessage.success("保存好了");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败了");
  } finally {
    profileSaving.value = false;
  }
}

/** ---------------- 导入导出 ---------------- */
const thisMonth = dayjs().format("YYYY-MM");
const exportRange = ref<[string, string]>([
  monthRange(thisMonth).from,
  monthRange(thisMonth).to
]);
const exporting = ref(false);
const importing = ref(false);
const importFile = ref<File | null>(null);
const importResult = ref<ImportResult | null>(null);

function onFilePicked(uploadFile: UploadFile) {
  importFile.value = uploadFile.raw ?? null;
  importResult.value = null;
}

async function onExport() {
  if (!props.user) return;
  exporting.value = true;
  try {
    await exportUserCsv(props.user.id, exportRange.value[0], exportRange.value[1]);
    ElMessage.success("导出好了");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "导出失败了");
  } finally {
    exporting.value = false;
  }
}

async function onImport() {
  if (!props.user || !importFile.value) return;
  importing.value = true;
  try {
    const res = await importUserCsv(props.user.id, importFile.value);
    importResult.value = res;
    importFile.value = null;
    ElMessage.success(`导入完成：成功 ${res.imported} 条，跳过 ${res.skipped} 条`);
    await loadTxns(1);
    emit("changed");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "导入失败了");
  } finally {
    importing.value = false;
  }
}

/** ---------------- 打开抽屉 ---------------- */
async function onOpen() {
  tab.value = "txns";
  page.value = 1;
  range.value = null;
  filterBook.value = null;
  includeDeleted.value = false;
  importResult.value = null;
  await loadMeta();
  await loadTxns(1);
  await loadProfile();
}
</script>

<style scoped>
.detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tabs {
  margin-top: 4px;
}

.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.io-block h4 {
  margin: 0 0 4px;
  font-size: 14px;
}

.gap {
  margin-left: 8px;
}
</style>
