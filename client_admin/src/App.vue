<script setup>
import { useRoute, useRouter } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()
const router = useRouter()

const operator = computed(() => localStorage.getItem('admin_operator') || 'admin')

function logout() {
  localStorage.removeItem('admin_token')
  localStorage.removeItem('admin_operator')
  router.push('/login')
}

const menus = [
  { path: '/dramas', label: '内容管理' },
  { path: '/tasks', label: 'AI 生成任务' },
  { path: '/audit', label: '审计日志' },
]
</script>

<template>
  <el-container class="app-shell">
    <el-aside width="200px" class="app-aside">
      <div class="app-title">短剧互动运营平台</div>
      <el-menu :default-active="route.path" router class="app-menu">
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          {{ m.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <div class="app-header-right">
          <span class="operator">操作者：{{ operator }}</span>
          <el-button size="small" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
html, body, #app { height: 100%; margin: 0; }
body { font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; }
.app-shell { height: 100%; }
.app-aside { background: #001529; }
.app-title { color: #fff; font-size: 15px; font-weight: 600; padding: 18px 16px; letter-spacing: 1px; }
.app-menu { border-right: none; background: transparent; --el-menu-text-color: #b7c0cd; --el-menu-hover-bg-color: #1f2d3d; --el-menu-active-color: #409eff; }
.app-header { background: #fff; border-bottom: 1px solid #e6e6e6; display: flex; align-items: center; justify-content: flex-end; }
.app-header-right { display: flex; align-items: center; gap: 12px; }
.operator { color: #606266; font-size: 13px; }
.app-main { background: #f5f7fa; }
</style>
