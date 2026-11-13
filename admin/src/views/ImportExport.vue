<template>
  <div class="page">
    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>导出账单</h2>
          <p class="sub">导出的 CSV 是 8 列口径，可以直接用 Excel 打开，也能再导入回来。</p>
        </div>
      </div>

      <el-form label-width="90px" class="io-form" @submit.prevent>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="到"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
          />
        </el-form-item>
        <el-form-item label="账本">
          <el-select v-model="bookId" placeholder="全部账本" clearable style="width: 220px">
            <el-option v-for="book in books" :key="book.id" :label="book.name" :value="book.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="exporting" @click="onExport">导出 CSV</el-button>
          <span class="muted" style="margin-left: 12px">表头：{{ CSV_HEADER.join(" / ") }}</span>
        </el-form-item>
      </el-form>
    </div>

    <div class="page-card">
      <div class="page-head">
        <div>
          <h2>导入账单</h2>
          <p class="sub">
            选一个 8 列 CSV 文件，账本、分类、账户会按名字自动补齐；重复的行会自动跳过。
          </p>
        </div>
      </div>

      <el-alert type="info" :closable="false" show-icon class="hint">
        <template #title>
          必须有「时间」列（格式 YYYY-MM-DD HH:mm:ss）和「金额」列；「收支」写「收入」算收入，其它算支出。
        </template>
      </el-alert>

      <div class="upload-row">
        <el-upload
          ref="uploadRef"
          :auto-upload="false"
          :limit="1"
          accept=".csv,text/csv"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
          :on-exceed="onExceed"
        >
          <el-button type="primary" plain>选择 CSV 文件</el-button>
        </el-upload>
        <el-button type="primary" :disabled="!file" :loading="importing" @click="onImport">开始导入</el-button>
      </div>

      <div v-if="result" class="result">
        <el-tag type="success" effect="dark">导入成功 {{ result.imported }} 条</el-tag>
        <el-tag v-if="result.skipped > 0" type="info" effect="plain" class="gap">
          跳过 {{ result.skipped }} 条
        </el-tag>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import dayjs from "dayjs";
import { ElMessage } from "element-plus";
import type { UploadFile, UploadInstance } from "element-plus";
import { CSV_HEADER, exportMyCsv, importMyCsv } from "@/api/io";
import { fetchMeta } from "@/api/meta";
import type { Book, ImportResult } from "@/api/types";
import { monthRange } from "@/utils/format";

const uploadRef = ref<UploadInstance>();
const books = ref<Book[]>([]);
const bookId = ref<number | null>(null);

const thisMonth = dayjs().format("YYYY-MM");
const range = ref<[string, string]>([
  monthRange(thisMonth).from,
  monthRange(thisMonth).to
]);

const file = ref<File | null>(null);
const exporting = ref(false);
const importing = ref(false);
const result = ref<ImportResult | null>(null);

function onFileChange(uploadFile: UploadFile) {
  file.value = uploadFile.raw ?? null;
  result.value = null;
}

function onFileRemove() {
  file.value = null;
}

function onExceed() {
  uploadRef.value?.clearFiles();
  ElMessage.warning("一次只能导入一个文件，先移除已选的文件");
}

async function onExport() {
  if (!range.value || range.value.length !== 2) {
    ElMessage.warning("先选一个时间范围");
    return;
  }
  exporting.value = true;
  try {
    await exportMyCsv(range.value[0], range.value[1], bookId.value);
    ElMessage.success("导出好了");
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "导出失败了");
  } finally {
    exporting.value = false;
  }
}

async function onImport() {
  if (!file.value) return;
  importing.value = true;
  try {
    const res = await importMyCsv(file.value);
    result.value = res;
    ElMessage.success(`导入完成：成功 ${res.imported} 条，跳过 ${res.skipped} 条`);
    uploadRef.value?.clearFiles();
    file.value = null;
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "导入失败了");
  } finally {
    importing.value = false;
  }
}

onMounted(async () => {
  try {
    const meta = await fetchMeta();
    books.value = meta.books;
  } catch {
    // 账本拉不到不影响导入导出
  }
});
</script>

<style scoped>
.io-form {
  max-width: 720px;
}

.hint {
  margin-bottom: 18px;
}

.upload-row {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}

.result {
  margin-top: 18px;
}

.gap {
  margin-left: 8px;
}
</style>
