<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 108 108"
    role="img"
    aria-label="小喵记账"
    class="miao-logo"
  >
    <title>小喵记账 MiaoLedger</title>
    <rect width="108" height="108" rx="24" ry="24" fill="#5AA9F0" />
    <g fill="none" stroke="#FFFFFF" stroke-linecap="round" stroke-linejoin="round">
      <path d="M39,43 a15,13.5 0 1 0 30,0 a15,13.5 0 1 0 -30,0" stroke-width="3" />
      <path d="M43.5,34 L41,24.5 L51.5,30.5" stroke-width="3" />
      <path d="M64.5,34 L67,24.5 L56.5,30.5" stroke-width="3" />
      <path d="M51,47.5 Q54,50.5 54,47.5 Q54,50.5 57,47.5" stroke-width="2.2" />
      <path d="M37,40.5 L29,38.5" stroke-width="2.2" />
      <path d="M37,45.5 L29,46.5" stroke-width="2.2" />
      <path d="M71,40.5 L79,38.5" stroke-width="2.2" />
      <path d="M71,45.5 L79,46.5" stroke-width="2.2" />
      <path d="M47.6,54.5 L46.6,61" stroke-width="3" />
      <path d="M60.4,54.5 L61.4,61" stroke-width="3" />
      <path d="M43,71 a11,11 0 1 0 22,0 a11,11 0 1 0 -22,0" stroke-width="3" />
      <path d="M50.4,66.6 L54,69.8 L57.6,66.6" stroke-width="2.4" />
      <path d="M54,69.8 L54,77.4" stroke-width="2.4" />
      <path d="M50.4,71.4 L57.6,71.4" stroke-width="2.2" />
      <path d="M50.4,74.6 L57.6,74.6" stroke-width="2.2" />
    </g>
    <g fill="#FFFFFF">
      <circle cx="49" cy="41" r="2" />
      <circle cx="59" cy="41" r="2" />
    </g>
  </svg>
</template>

<script setup lang="ts">
/** 品牌矢量图标：与手机端 / README 用同一份图形（蓝底 + 白色线条小喵抱铜钱）。 */
withDefaults(defineProps<{ size?: number | string }>(), { size: 40 });
</script>

<style scoped>
.miao-logo {
  display: block;
  flex: none;
}
</style>
