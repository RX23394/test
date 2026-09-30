<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { storeToRefs } from "pinia";

import {
  type ManagedUser,
  type ManagedUserCreate,
  type UserRole,
  useAdminStore,
} from "@/stores/admin";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();
const adminStore = useAdminStore();
const { users, loading, saving } = storeToRefs(adminStore);
const search = ref("");
const dialogVisible = ref(false);
const loadError = ref("");
const form = reactive<ManagedUserCreate>({
  username: "",
  password: "",
  role: "user",
});

const filteredUsers = computed<ManagedUser[]>(() => {
  const term = search.value.trim().toLowerCase();
  if (!term) {
    return users.value;
  }
  return users.value.filter(
    (user) =>
      user.username.toLowerCase().includes(term) || user.role.includes(term),
  );
});
const activeCount = computed<number>(
  () => users.value.filter((user) => user.is_active).length,
);
const adminCount = computed<number>(
  () => users.value.filter((user) => user.role === "admin").length,
);

/** Load all managed users from the administrator API. */
async function loadUsers(): Promise<void> {
  loadError.value = "";
  try {
    await adminStore.loadUsers();
  } catch {
    loadError.value = "用户列表加载失败，请稍后重试";
    ElMessage.error("用户列表加载失败，请稍后重试");
  }
}

/** Open a clean new-user form. */
function openCreateDialog(): void {
  form.username = "";
  form.password = "";
  form.role = "user";
  dialogVisible.value = true;
}

/** Validate and create a new user account. */
async function submitCreate(): Promise<void> {
  if (!/^[A-Za-z0-9_.-]{3,64}$/.test(form.username)) {
    ElMessage.warning("用户名需为 3-64 位字母、数字、点、短横线或下划线");
    return;
  }
  if (form.password.length < 8) {
    ElMessage.warning("密码至少需要 8 位");
    return;
  }
  try {
    await adminStore.addUser({ ...form });
    dialogVisible.value = false;
    ElMessage.success("用户已新增");
  } catch (error: unknown) {
    const message = adminStore.errorMessage(error);
    ElMessage.error(
      message === "Username already exists" ? "用户名已存在" : "新增用户失败",
    );
  }
}

/** Confirm and toggle whether a user account is active. */
async function toggleStatus(user: ManagedUser): Promise<void> {
  const nextActive = !user.is_active;
  const action = nextActive ? "恢复" : "停用";
  try {
    await ElMessageBox.confirm(
      `${action}“${user.username}”账号？`,
      `${action}用户`,
      { confirmButtonText: action, cancelButtonText: "取消", type: "warning" },
    );
    await adminStore.setUserActive(user.id, nextActive);
    ElMessage.success(`用户已${action}`);
  } catch (error: unknown) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(adminStore.errorMessage(error) ?? `${action}用户失败`);
    }
  }
}

/** Persist a role selected in the user table. */
async function changeRole(user: ManagedUser, role: UserRole): Promise<void> {
  const previousRole: UserRole = user.is_admin ? "admin" : "user";
  try {
    await adminStore.setUserRole(user.id, role);
    ElMessage.success("用户角色已更新");
  } catch (error: unknown) {
    user.role = previousRole;
    ElMessage.error(adminStore.errorMessage(error) ?? "角色更新失败");
  }
}

/** Format an ISO account date for the local browser locale. */
function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

/** Return a two-character avatar label for a username. */
function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

onMounted(loadUsers);
</script>

<template>
  <section class="users-page">
    <header class="page-heading">
      <div>
        <p class="eyebrow">ADMINISTRATION</p>
        <h2>用户管理</h2>
        <p>新增账号、分配角色并控制用户访问状态。</p>
      </div>
      <div class="summary">
        <div><strong>{{ users.length }}</strong><span>全部用户</span></div>
        <div><strong>{{ activeCount }}</strong><span>正常使用</span></div>
        <div><strong>{{ adminCount }}</strong><span>管理员</span></div>
      </div>
    </header>

    <div class="users-card">
      <div class="toolbar">
        <div>
          <h3>系统用户</h3>
          <span>管理员可新增、停用、恢复用户并调整角色</span>
        </div>
        <div class="toolbar-actions">
          <el-input v-model="search" clearable placeholder="搜索用户名或角色" />
          <el-button type="primary" @click="openCreateDialog">+ 新增用户</el-button>
        </div>
      </div>

      <el-alert
        v-if="loadError"
        class="state-error"
        type="error"
        :title="loadError"
        show-icon
        :closable="false"
      >
        <el-button size="small" @click="loadUsers">重新加载</el-button>
      </el-alert>

      <div class="table-wrap">
        <div v-if="loading" class="state-skeleton">
          <el-skeleton :rows="5" animated />
        </div>
        <table v-else>
          <thead>
            <tr><th>用户</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="user in filteredUsers" :key="user.id">
              <td>
                <div class="user-cell">
                  <span class="avatar" :class="{ admin: user.role === 'admin' }">{{ initials(user.username) }}</span>
                  <div><strong>{{ user.username }}</strong><small>ID · {{ user.id }}<template v-if="user.id === authStore.user?.id"> · 当前账号</template></small></div>
                </div>
              </td>
              <td>
                <el-select
                  v-model="user.role"
                  class="role-select"
                  :disabled="user.id === authStore.user?.id"
                  @change="changeRole(user, $event)"
                >
                  <el-option label="admin" value="admin" />
                  <el-option label="user" value="user" />
                </el-select>
              </td>
              <td><span class="status-pill" :class="user.is_active ? 'active' : 'inactive'"><i />{{ user.is_active ? "正常" : "已停用" }}</span></td>
              <td>{{ formatDate(user.created_at) }}</td>
              <td>
                <el-button
                  link
                  :type="user.is_active ? 'danger' : 'success'"
                  :disabled="user.id === authStore.user?.id"
                  @click="toggleStatus(user)"
                >
                  {{ user.is_active ? "停用" : "恢复" }}
                </el-button>
              </td>
            </tr>
            <tr v-if="!loading && filteredUsers.length === 0">
              <td colspan="5" class="empty-state">没有匹配的用户。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" width="min(480px, 92vw)" title="新增用户">
      <el-form label-position="top" @submit.prevent="submitCreate">
        <el-form-item label="用户名">
          <el-input v-model="form.username" maxlength="64" placeholder="例如 network.user" />
        </el-form-item>
        <el-form-item label="初始密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="角色">
          <el-radio-group v-model="form.role" class="role-options">
            <el-radio-button value="user">user</el-radio-button>
            <el-radio-button value="admin">admin</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">新增用户</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.users-page { display: grid; gap: 22px; max-width: 1440px; margin: 0 auto; }
.page-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; }
.eyebrow { margin: 0 0 7px; color: #2563eb; font-size: .72rem; font-weight: 800; letter-spacing: .13em; }
.page-heading h2 { margin: 0; color: #172033; font-size: 1.75rem; letter-spacing: -.03em; }
.page-heading p:not(.eyebrow) { margin: 8px 0 0; color: #64748b; }
.summary { display: flex; gap: 10px; }
.summary div { min-width: 102px; padding: 13px 16px; border: 1px solid #e2e8f0; border-radius: 12px; background: #fff; }
.summary strong, .summary span { display: block; }
.summary strong { color: #172033; font-size: 1.25rem; }
.summary span { margin-top: 2px; color: #94a3b8; font-size: .76rem; }
.users-card { overflow: hidden; border: 1px solid #e2e8f0; border-radius: 16px; background: #fff; box-shadow: 0 8px 24px rgb(15 23 42 / 4%); }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px 24px; border-bottom: 1px solid #edf0f4; }
.toolbar h3 { margin: 0; color: #1e293b; font-size: 1rem; }
.toolbar span { display: block; margin-top: 4px; color: #94a3b8; font-size: .75rem; }
.toolbar-actions { display: flex; width: min(490px, 100%); gap: 10px; }
.toolbar-actions .el-input { flex: 1; }
.table-wrap { overflow-x: auto; }
table { width: 100%; min-width: 760px; border-collapse: collapse; }
th { padding: 12px 20px; color: #7b8799; background: #fafbfc; font-size: .72rem; font-weight: 700; letter-spacing: .04em; text-align: left; }
td { padding: 15px 20px; border-top: 1px solid #f0f2f5; color: #536174; font-size: .82rem; }
.user-cell { display: flex; align-items: center; gap: 12px; min-width: 220px; }
.avatar { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 11px; color: #475569; background: #eef2f7; font-size: .7rem; font-weight: 800; }
.avatar.admin { color: #1d4ed8; background: #dbeafe; }
.user-cell strong, .user-cell small { display: block; }
.user-cell strong { color: #273449; }
.user-cell small { margin-top: 4px; color: #94a3b8; font-size: .68rem; }
.role-select { width: 108px; }
.status-pill { display: inline-flex; align-items: center; gap: 7px; padding: 5px 9px; border-radius: 999px; font-size: .7rem; font-weight: 700; }
.status-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.status-pill.active { color: #15803d; background: #ecfdf3; }
.status-pill.inactive { color: #64748b; background: #f1f5f9; }
.empty-state { padding: 52px 20px; color: #94a3b8; text-align: center; }
.role-options { width: 100%; }
.role-options :deep(.el-radio-button) { width: 50%; }
.role-options :deep(.el-radio-button__inner) { width: 100%; }
@media (max-width: 900px) { .page-heading { align-items: flex-start; flex-direction: column; } .summary { width: 100%; } .summary div { flex: 1; min-width: 0; } .toolbar { align-items: stretch; flex-direction: column; } .toolbar-actions { width: 100%; } }
@media (max-width: 560px) { .summary { gap: 6px; } .summary div { padding: 10px; } .toolbar-actions { flex-direction: column; } }
</style>
