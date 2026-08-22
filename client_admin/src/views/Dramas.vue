<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api, { errorDetail } from '../api'

const router = useRouter()
const loading = ref(false)
const dramas = ref([])

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/dramas')
    dramas.value = data
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

function openDrama(drama) {
  router.push({ path: '/episodes', query: { drama_id: drama.id } })
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>内容管理</h2>
    </div>
    <el-table v-loading="loading" :data="dramas" border stripe @row-click="openDrama" style="cursor: pointer">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column label="封面" width="80">
        <template #default="{ row }">
          <el-image :src="row.poster" fit="cover" style="width: 48px; height: 64px; border-radius: 4px">
            <template #error><div style="width:48px;height:64px;background:#eee;border-radius:4px" /></template>
          </el-image>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="短剧名称" min-width="160" />
      <el-table-column prop="episode_count" label="剧集数" width="90" align="center" />
      <el-table-column prop="published_count" label="已发布高光" width="110" align="center" />
      <el-table-column prop="total_interactions" label="互动总量" width="110" align="center" />
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click.stop="openDrama(row)">查看剧集</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-head h2 { margin: 0; }
</style>
