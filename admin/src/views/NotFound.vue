<template>
  <div class="page">
    <div class="page-card notfound">
      <h2>页面走丢了</h2>
      <p class="muted">这个地址不存在，可能是链接过期或者输错了。</p>
      <el-button type="primary" @click="router.replace('/books')">回到我的账本</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<style scoped>
.notfound {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 320px;
  text-align: center;
}

.notfound h2 {
  margin: 0;
  font-size: 20px;
}
</style>
