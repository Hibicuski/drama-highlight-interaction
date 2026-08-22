<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api, { errorDetail } from '../api'

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const targetType = ref('')
const targetId = ref('')

const OPERATION_LABELS = {
  create_version: '新建版本',
  update_version: '编辑版本',
  publish: '发布',
  rollback: '回滚',
  generate: '生成任务',
  retry: '重试任务',
  scan: '重新扫描',
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/audit-logs', {
      params: {
        target_type: targetType.value || undefined,
        target_id: targetId.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
    })
    logs.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

function fmtTime(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function fmtJson(value) {
  return value ? JSON.stringify(value, null, 2) : '-'
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <h2>审计日志</h2>
    </div>
    <el-card shadow="never">
      <el-form inline style="margin-bottom: 8px">
        <el-form-item label="目标类型">
          <el-select v-model="targetType" placeholder="全部" style="width: 180px" clearable @change="() => { page = 1; load() }">
            <el-option value="manifest_version" label="Manifest 版本" />
            <el-option value="generation_task" label="生成任务" />
            <el-option value="episode" label="剧集" />
            <el-option value="drama" label="短剧" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标 ID">
          <el-input v-model="targetId" placeholder="版本/任务/剧集 ID" style="width: 160px" clearable @keyup.enter="() => { page = 1; load() }" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="() => { page = 1; load() }">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="loading" :data="logs" border stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="log-diff">
              <div>
                <div class="diff-label">变更前 (before)</div>
                <pre>{{ fmtJson(row.before) }}</pre>
              </div>
              <div>
                <div class="diff-label">变更后 (after)</div>
                <pre>{{ fmtJson(row.after) }}</pre>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="80" align="center" />
        <el-table-column label="操作" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small">{{ OPERATION_LABELS[row.operation] || row.operation }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="操作者" width="120" align="center" />
        <el-table-column label="目标" min-width="200">
          <template #default="{ row }">{{ row.target_type }} / {{ row.target_id }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
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
.log-diff { display: flex; gap: 24px; padding: 4px 24px 4px 48px; }
.log-diff > div { flex: 1; }
.diff-label { color: #606266; font-size: 13px; margin-bottom: 4px; }
.log-diff pre { background: #f5f7fa; border-radius: 4px; padding: 8px; font-size: 12px; max-height: 240px; overflow: auto; margin: 0; }
</style>
