<template>
  <div class="app-layout">
    <el-container style="min-height: 100vh">
      <el-header class="app-header">
        <div class="brand">
          <img src="@/assets/imgs/logo.png" alt="" />
          <div>
            <strong>智能实验室预约系统</strong>
            <small>实验室 · 设备 · 智能预约</small>
          </div>
        </div>
        <div>
          <el-dropdown @command="handleCommand">
            <button type="button" class="user-menu">
              <el-avatar
                :size="34"
                :src="userInfo?.avatar ? '/uploads/' + userInfo.avatar : undefined"
              >
                {{ userInfo?.name?.slice(0, 1) || '用' }}
              </el-avatar>
              <span class="user-name">{{ userInfo?.name }}</span>
              <el-icon class="user-chevron"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="password">修改密码</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-container class="app-body">
        <el-aside class="app-aside" width="var(--sidebar-width)">
          <p class="nav-caption">工作台</p>
          <el-menu router class="app-nav" :default-active="route.path">
            <el-menu-item index="/manager/home">
              <el-icon><icon-menu /></el-icon>
              <span>系统首页</span>
            </el-menu-item>
            <el-menu-item index="/manager/ai-chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>AI智能助手</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'student'" index="/manager/lablist">
              <el-icon><OfficeBuilding /></el-icon>
              <span>实验室列表</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'student'" index="/manager/my-reservation">
              <el-icon><Tickets /></el-icon>
              <span>我的预约</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'admin'" index="/manager/lab">
              <el-icon><House /></el-icon>
              <span>实验室管理</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'admin'" index="/manager/equipment">
              <el-icon><Setting /></el-icon>
              <span>设备列表管理</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'admin'" index="/manager/audit-reservation">
              <el-icon><DocumentChecked /></el-icon>
              <span>预约审核</span>
            </el-menu-item>
            <el-menu-item v-if="userInfo?.role === 'admin'" index="/manager/user">
              <el-icon><User /></el-icon>
              <span>用户管理</span>
            </el-menu-item>
          </el-menu>
          <div class="sidebar-note">
            <span class="note-dot"></span><span>让实验预约更简单</span>
          </div>
        </el-aside>
        <el-main class="app-main">
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import router from '@/router'
import { useRoute } from 'vue-router'
import { logout } from '@/utils/auth'
import {
  Menu as IconMenu,
  House,
  Setting,
  User,
  OfficeBuilding,
  Tickets,
  DocumentChecked,
  ChatDotRound,
  ArrowDown
} from '@element-plus/icons-vue'
import { useUser } from '@/utils/user'

const { userInfo } = useUser()
const route = useRoute()

const handleCommand = (command) => {
  if (command === 'profile') {
    router.push('/manager/profile')
  } else if (command === 'password') {
    router.push('/manager/password')
  } else if (command === 'logout') {
    logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.app-layout {
  --sidebar-width: 208px;
}
.app-header {
  height: 72px;
  padding: 0 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: #fff;
  border-bottom: 1px solid #e9edf5;
}
.brand {
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand img {
  width: 40px;
  height: 40px;
  padding: 4px;
  object-fit: contain;
  background: #f1f5ff;
  border-radius: 12px;
}
.brand strong {
  display: block;
  font-size: 17px;
  font-weight: 700;
  color: #202c43;
}
.brand small {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #8a94a7;
  letter-spacing: 1px;
}
.user-menu {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 9px;
  border: 0;
  border-radius: 10px;
  color: #4c5871;
  background: transparent;
  font: inherit;
  cursor: pointer;
}
.user-menu:hover {
  background: #f5f7fc;
}
.user-menu .el-avatar {
  background: #eaf0ff;
  color: #4166e8;
  font-weight: 600;
}
.user-name {
  font-size: 13px;
}
.user-chevron {
  font-size: 11px;
  color: #9aa5b8;
}
.app-body {
  min-height: calc(100vh - 72px);
}
.app-aside {
  background: #fff;
  border-right: 1px solid #e9edf5;
  padding: 25px 12px 20px;
  display: flex;
  flex-direction: column;
}
.nav-caption {
  margin: 0 16px 14px;
  font-size: 11px;
  color: #9aa4b5;
  letter-spacing: 2px;
}
.app-nav {
  border: 0;
  --el-menu-hover-bg-color: #f5f7fc;
}
.app-nav .el-menu-item {
  height: 46px;
  margin-bottom: 7px;
  padding: 0 16px !important;
  gap: 9px;
  border-radius: 10px;
  color: #68748a;
  font-size: 13px;
}
.app-nav .el-icon {
  margin-right: 0;
  font-size: 18px;
}
.app-nav .el-menu-item.is-active {
  color: #4166e8;
  background: #edf2ff;
  font-weight: 600;
}
.sidebar-note {
  margin: auto 13px 0;
  padding-top: 30px;
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #a1aabb;
  white-space: nowrap;
}
.note-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #92a8e8;
}
.app-main {
  min-width: 0;
  padding: 24px;
  background: #f5f7fb;
}
@media (max-width: 768px) {
  .app-layout {
    --sidebar-width: 68px;
  }
  .app-header {
    height: 64px;
    padding: 0 16px;
  }
  .brand strong {
    font-size: 14px;
  }
  .brand small,
  .user-name,
  .user-chevron,
  .nav-caption,
  .sidebar-note {
    display: none;
  }
  .app-nav .el-menu-item span {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .brand img {
    width: 34px;
    height: 34px;
    border-radius: 10px;
  }
  .app-body {
    min-height: calc(100vh - 64px);
  }
  .app-aside {
    padding: 18px 9px;
  }
  .app-nav .el-menu-item {
    padding: 0 !important;
    justify-content: center;
  }
  .app-main {
    padding: 16px;
  }
}
</style>
