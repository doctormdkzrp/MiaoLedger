<template>
  <div class="layout">
    <aside class="sidebar" :class="{ collapsed: collapsed }">
      <div class="brand" @click="router.push('/books')">
        <MiaoLogo :size="26" />
        <span v-show="!collapsed" class="brand-text">小喵记账</span>
      </div>

      <el-menu
        class="menu"
        :collapse="collapsed"
        :default-active="activePath"
        background-color="transparent"
        text-color="#c3ccd8"
        active-text-color="#8ecbf7"
        :collapse-transition="false"
        router
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-foot">
        <el-button text class="collapse-btn" @click="collapsed = !collapsed">
          <el-icon><component :is="collapsed ? Expand : Fold" /></el-icon>
          <span v-show="!collapsed">收起菜单</span>
        </el-button>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <h1 class="page-title">{{ pageTitle }}</h1>
        </div>
        <div class="topbar-right">
          <el-tag v-if="userStore.isAdmin" type="warning" effect="plain" size="small">管理员</el-tag>
          <el-tag v-else type="info" effect="plain" size="small">普通用户</el-tag>
          <span class="who">{{ userStore.displayName }}</span>
          <el-dropdown trigger="click" @command="onCommand">
            <span class="avatar">{{ initial }}</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="account">我的账号</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>

      <footer class="footer">小喵记账 · 管理台</footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { Expand, Fold } from "@element-plus/icons-vue";
import MiaoLogo from "@/components/MiaoLogo.vue";
import { useUserStore } from "@/stores";

interface MenuItem {
  path: string;
  title: string;
  icon: string;
  roles?: Array<"admin" | "user">;
}

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();
const collapsed = ref(false);

// 登录态以 localStorage 为准，进布局时再同步一次，避免多标签页状态错位
onMounted(() => userStore.hydrate());

const allMenus: MenuItem[] = [
  { path: "/books", title: "我的账本", icon: "Notebook" },
  { path: "/txns", title: "我的账单", icon: "Tickets" },
  { path: "/io", title: "导入导出", icon: "Upload" },
  { path: "/ai", title: "我的 AI 提示词", icon: "MagicStick" },
  { path: "/account", title: "我的账号", icon: "User" },
  { path: "/admin/users", title: "用户管理", icon: "UserFilled", roles: ["admin"] }
];

/** 非管理员看不到「用户管理」。 */
const menus = computed(() =>
  allMenus.filter(item => !item.roles || (userStore.user && item.roles.includes(userStore.user.role)))
);

const activePath = computed(() => route.path);

const pageTitle = computed(() => (route.meta.title as string) || "小喵记账");

const initial = computed(() => {
  const name = userStore.displayName;
  return name ? name.slice(0, 1).toUpperCase() : "?";
});

async function onCommand(command: string) {
  if (command === "account") {
    router.push("/account");
    return;
  }
  if (command === "logout") {
    try {
      await ElMessageBox.confirm("确定要退出登录吗？", "退出登录", {
        confirmButtonText: "退出",
        cancelButtonText: "再想想",
        type: "warning"
      });
    } catch {
      return;
    }
    await userStore.logout();
    ElMessage.success("已经退出了");
    router.replace("/login");
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  width: 216px;
  flex: 0 0 216px;
  background: var(--miao-side-bg);
  transition: width 0.18s ease, flex-basis 0.18s ease;
}

.sidebar.collapsed {
  width: 64px;
  flex-basis: 64px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 18px;
  cursor: pointer;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.brand-text {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  letter-spacing: 0.5px;
}

.menu {
  flex: 1;
  border-right: none;
  padding: 8px 0;
  overflow-y: auto;
}

.menu :deep(.el-menu-item) {
  height: 44px;
  line-height: 44px;
  margin: 2px 10px;
  border-radius: 8px;
}

.menu :deep(.el-menu-item:hover) {
  background: var(--miao-side-bg-soft) !important;
}

.menu :deep(.el-menu-item.is-active) {
  background: rgba(90, 169, 240, 0.18) !important;
  font-weight: 600;
}

.sidebar-foot {
  padding: 8px 10px 12px;
}

.collapse-btn {
  width: 100%;
  justify-content: flex-start;
  color: #8891a1;
}

.main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #eceef2;
}

.page-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.who {
  font-size: 14px;
  color: var(--miao-text);
}

.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--miao-primary-soft);
  color: var(--el-color-primary);
  font-weight: 600;
  cursor: pointer;
  outline: none;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px 28px;
}

.footer {
  padding: 10px 24px 14px;
  text-align: right;
  font-size: 12px;
  color: #9aa2af;
}
</style>
