<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorDetail } from '../api'

const router = useRouter()

const loading = ref(false)
const autoRefresh = ref(true)
const tasks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')
const submitting = ref(false)
const dramas = ref([])
const selectedDramaId = ref(null)
const episodes = ref([])
const selectedContentId = ref('')
let timer = null

const STATUS_MAP = {
  pending: { label: '排队中', type: 'info' },
  running: { label: '执行中', type: 'warning' },
  succeeded: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/generation/tasks', {
      params: { status: statusFilter.value || undefined, page: page.value, page_size: pageSize.value },
    })
    tasks.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

async function loadDramas() {
  try {
    const { data } = await api.get('/dramas')
    dramas.value = data
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

async function loadEpisodes() {
  if (!selectedDramaId.value) {
    episodes.value = []
    return
  }
  try {
    const { data } = await api.get('/episodes', { params: { drama_id: selectedDramaId.value, page_size: 100 } })
    episodes.value = data.items
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

async function submitTask() {
  if (!selectedContentId.value) {
    ElMessage.warning('请先选择剧集')
    return
  }
  submitting.value = true
  try {
    const { data } = await api.post('/generation/tasks', { content_id: selectedContentId.value })
    ElMessage.success(`任务已受理（#${data.task_id}）`)
    selectedContentId.value = ''
    page.value = 1
    await load()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    submitting.value = false
  }
}

async function retry(task) {
  try {
    await ElMessageBox.confirm(`重试任务 #${task.id}？`, '确认重试', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.post(`/generation/tasks/${task.id}/retry`)
    ElMessage.success('已重新排队')
    await load()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

function openEditor(task) {
  router.push(`/editor/${task.content_id}`)
}

function fmtTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

onMounted(() => {
  load()
  loadDramas()
  timer = setInterval(() => {
    if (autoRefresh.value) load()
  }, 3000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div>
    <div class="page-head">
      <h2>AI 生成任务</h2>
      <el-switch v-model="autoRefresh" active-text="自动刷新(3s)" />
    </div>

    <!-- 新建任务 -->
    <el-card shadow="never" style="margin-bottom: 12px">
      <el-form inline>
        <el-form-item label="短剧">
          <el-select v-model="selectedDramaId" placeholder="选择短剧" style="width: 180px" @change="loadEpisodes">
            <el-option v-for="d in dramas" :key="d.id" :value="d.id" :label="d.title" />
          </el-select>
        </el-form-item>
        <el-form-item label="剧集">
          <el-select v-model="selectedContentId" placeholder="选择剧集" style="width: 260px" filterable>
            <el-option v-for="e in episodes" :key="e.content_id" :value="e.content_id" :label="`第${e.episode_index}集 · ${e.title}`" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitTask">生成高光候选</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 任务列表 -->
    <el-card shadow="never">
      <div style="margin-bottom: 8px">
        <el-radio-group v-model="statusFilter" @change="() => { page = 1; load() }">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="pending">排队中</el-radio-button>
          <el-radio-button value="running">执行中</el-radio-button>
          <el-radio-button value="succeeded">成功</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
      </div>
      <el-table v-loading="loading" :data="tasks" border stripe>
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="episode_id" label="剧集ID" width="80" align="center" />
        <el-table-column prop="relative_path" label="视频路径" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_MAP[row.status]?.type || 'info'" size="small">
              {{ STATUS_MAP[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="重试" width="90" align="center">
          <template #default="{ row }">{{ row.retry_count }}/{{ row.max_retry }}</template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span :style="{ color: row.error_message ? '#f56c6c' : '#909399' }">{{ row.error_message || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" align="center">
          <template #default="{ row }">
            <el-button v-if="row.status === 'failed'" size="small" @click="retry(row)">重试</el-button>
            <el-button v-if="row.created_version_id" size="small" type="primary" link @click="openEditor(row)">打开草稿</el-button>
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
    </el-card>
  </div>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-head h2 { margin: 0; }
</style>
