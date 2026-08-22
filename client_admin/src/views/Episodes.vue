<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorDetail } from '../api'

const props = defineProps({ dramaId: { type: Number, default: 0 } })
const router = useRouter()

const loading = ref(false)
const episodes = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const generating = ref({})

const STATUS_MAP = {
  none: { label: '无高光', type: 'info' },
  draft: { label: '草稿', type: 'warning' },
  reviewing: { label: '审核中', type: 'warning' },
  published: { label: '已发布', type: 'success' },
}

function fmtDuration(ms) {
  if (!ms) return '-'
  const s = Math.round(ms / 1000)
  const m = Math.floor(s / 60)
  return `${m}分${String(s % 60).padStart(2, '0')}秒`
}

async function load() {
  if (!props.dramaId) return
  loading.value = true
  try {
    const { data } = await api.get('/episodes', {
      params: { drama_id: props.dramaId, page: page.value, page_size: pageSize.value },
    })
    episodes.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

function openEditor(row) {
  router.push(`/editor/${row.content_id}`)
}

async function triggerGeneration(row) {
  try {
    await ElMessageBox.confirm(`为「${row.title}」生成高光候选？（AI 流水线，耗时较长）`, '确认生成', {
      type: 'warning',
    })
  } catch {
    return
  }
  generating.value[row.content_id] = true
  try {
    const { data } = await api.post('/generation/tasks', { content_id: row.content_id })
    ElMessage.success(`任务已受理（#${data.task_id}）`)
    router.push('/tasks')
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    generating.value[row.content_id] = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>剧集列表</h2>
      <el-button @click="router.push('/dramas')">返回短剧列表</el-button>
    </div>
    <el-table v-loading="loading" :data="episodes" border stripe>
      <el-table-column prop="episode_index" label="集数" width="80" align="center" />
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column label="时长" width="110" align="center">
        <template #default="{ row }">{{ fmtDuration(row.duration_ms) }}</template>
      </el-table-column>
      <el-table-column label="Manifest 状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="(STATUS_MAP[row.manifest_status] || STATUS_MAP.none).type" size="small">
            {{ (STATUS_MAP[row.manifest_status] || STATUS_MAP.none).label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="highlight_count" label="高光数" width="90" align="center" />
      <el-table-column prop="interaction_count" label="互动数" width="90" align="center" />
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openEditor(row)">编辑器</el-button>
          <el-button
            size="small"
            :loading="!!generating[row.content_id]"
            @click="triggerGeneration(row)"
          >
            生成高光
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination
      style="margin-top: 12px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(p) => { page = p; load() }"
    />
  </div>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-head h2 { margin: 0; }
</style>
