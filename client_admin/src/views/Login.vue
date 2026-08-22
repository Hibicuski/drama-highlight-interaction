<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const router = useRouter()

const token = ref(localStorage.getItem('admin_token') || '')
const operator = ref(localStorage.getItem('admin_operator') || '')
const loading = ref(false)

function submit() {
  if (!token.value.trim()) {
    ElMessage.warning('请输入管理端 Token（服务器 ADMIN_TOKEN）')
    return
  }
  loading.value = true
  // 用 GET /dramas 验证 token 是否有效
  api
    .get('/dramas', { headers: { Authorization: `Bearer ${token.value.trim()}` } })
    .then(() => {
      localStorage.setItem('admin_token', token.value.trim())
      localStorage.setItem('admin_operator', operator.value.trim() || 'admin')
      ElMessage.success('登录成功')
      router.push(route.query.redirect || '/')
    })
    .catch((error) => {
      ElMessage.error(error.response?.status === 401 ? 'Token 无效' : error.message || '连接失败')
    })
    .finally(() => {
      loading.value = false
    })
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 class="login-title">短剧互动内容运营平台</h2>
      <p class="login-sub">管理端（/admin/api 由 ADMIN_TOKEN 保护）</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="Admin Token">
          <el-input v-model="token" type="password" show-password placeholder="服务器 ADMIN_TOKEN" />
        </el-form-item>
        <el-form-item label="操作者昵称（写入审计日志）">
          <el-input v-model="operator" placeholder="默认 admin" />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">
          进入平台
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f2f5;
}
.login-card { width: 380px; padding: 12px 8px; }
.login-title { margin: 0 0 4px; text-align: center; }
.login-sub { margin: 0 0 20px; text-align: center; color: #909399; font-size: 13px; }
</style>
