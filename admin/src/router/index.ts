import { createRouter, createWebHashHistory } from "vue-router";
import type { RouteRecordRaw } from "vue-router";
import { ElMessage } from "element-plus";
import { isLogged, getUser } from "@/utils/auth";
import MainLayout from "@/layouts/MainLayout.vue";

declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    icon?: string;
    /** 需要的角色；不写表示所有登录用户都能看。 */
    roles?: Array<"admin" | "user">;
    /** 不在侧边菜单里显示。 */
    hidden?: boolean;
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "Login",
    component: () => import("@/views/Login.vue"),
    meta: { title: "登录", hidden: true }
  },
  {
    path: "/",
    component: MainLayout,
    redirect: "/books",
    children: [
      {
        path: "/books",
        name: "Books",
        component: () => import("@/views/Books.vue"),
        meta: { title: "我的账本", icon: "Notebook" }
      },
      {
        path: "/txns",
        name: "Txns",
        component: () => import("@/views/Txns.vue"),
        meta: { title: "我的账单", icon: "Tickets" }
      },
      {
        path: "/io",
        name: "ImportExport",
        component: () => import("@/views/ImportExport.vue"),
        meta: { title: "导入导出", icon: "Upload" }
      },
      {
        path: "/ai",
        name: "AiProfile",
        component: () => import("@/views/AiProfile.vue"),
        meta: { title: "我的 AI 提示词", icon: "MagicStick" }
      },
      {
        path: "/account",
        name: "Account",
        component: () => import("@/views/Account.vue"),
        meta: { title: "我的账号", icon: "User" }
      },
      {
        path: "/admin/users",
        name: "AdminUsers",
        component: () => import("@/views/admin/Users.vue"),
        meta: { title: "用户管理", icon: "UserFilled", roles: ["admin"] }
      }
    ]
  },
  {
    path: "/:pathMatch(.*)*",
    name: "NotFound",
    component: () => import("@/views/NotFound.vue"),
    meta: { title: "页面不存在", hidden: true }
  }
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
});

router.beforeEach(to => {
  document.title = to.meta.title ? `${to.meta.title} · 小喵记账` : "小喵记账 管理台";

  const logged = isLogged();

  if (to.path === "/login") {
    return logged ? { path: "/books" } : true;
  }

  if (!logged) {
    return { path: "/login", query: to.fullPath === "/" ? undefined : { redirect: to.fullPath } };
  }

  const roles = to.meta.roles;
  if (roles && roles.length > 0) {
    const role = getUser()?.role;
    if (!role || !roles.includes(role)) {
      ElMessage.error("没有权限访问这个页面");
      return { path: "/books" };
    }
  }

  return true;
});

export default router;
