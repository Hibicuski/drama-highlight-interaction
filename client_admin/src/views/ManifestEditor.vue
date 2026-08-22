<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { errorDetail } from '../api'

const props = defineProps({ contentId: { type: String, required: true } })
const router = useRouter()

// 与后端 manifest_store 白名单保持一致（新增枚举需同步）
const HIGHLIGHT_TYPES = ['satisfying', 'twist', 'revenge', 'slap-face', 'funny', 'sweet', 'suspense', 'reveal', 'conflict', 'famous-scene']
const TEMPLATES = ['dual-button', 'poll', 'tap-boost']
const EFFECTS = ['particle-burst', 'ratio-reveal', 'pulse']
const TONES = ['positive', 'negative', 'shocked', 'funny', 'confused', 'support', 'calm']
const ICONS = ['heart', 'fire', 'shock', 'laugh', 'question', 'check', 'boost']
const STATUS_MAP = {
  draft: { label: '草稿', type: 'warning' },
  reviewing: { label: '审核中', type: 'warning' },
  published: { label: '已发布', type: 'success' },
  archived: { label: '已归档', type: 'info' },
}

const loading = ref(false)
const saving = ref(false)
const episode = ref(null)
const versions = ref([])
const selectedVersionId = ref(null)
const currentVersion = ref(null)
const form = reactive({ status: 'draft', highlights: [] })

// ---------- 视频 ----------
const videoRef = ref(null)
const currentTime = ref(0)
const videoDuration = ref(0)

function meta() {
  videoDuration.value = videoRef.value?.duration || episode.value?.duration_ms / 1000 || 0
}
function tick() {
  currentTime.value = videoRef.value?.currentTime || 0
}
function seek(ms) {
  if (!videoRef.value) return
  videoRef.value.currentTime = ms / 1000
  videoRef.value.play()
}
function fmt(ms) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}
const durationSeconds = computed(() => videoDuration.value || (episode.value?.duration_ms || 0) / 1000)

// ---------- 版本加载 ----------
function flatten(manifest) {
  return (manifest.highlights || []).map((h) => ({
    id: h.id,
    start_ms: h.start_ms,
    end_ms: h.end_ms,
    type: h.type,
    intensity: h.intensity ?? 1,
    template: h.template,
    title: h.payload?.title || '',
    effect: h.payload?.effect || 'pulse',
    actions: (h.payload?.actions || []).map((a) => ({ key: a.key, label: a.label, tone: a.tone, icon: a.icon })),
  }))
}

function buildPayload() {
  return {
    content_id: props.contentId,
    version: '0.2.0',
    highlights: form.highlights.map((h, i) => ({
      id: h.id || `candidate-${i + 1}`,
      start_ms: Number(h.start_ms),
      end_ms: Number(h.end_ms),
      type: h.type,
      intensity: Number(h.intensity),
      template: h.template,
      payload: {
        title: h.title,
        actions: h.actions.map((a) => ({ key: a.key, label: a.label, tone: a.tone, icon: a.icon })),
        effect: h.effect,
      },
    })),
  }
}

async function loadVersion(versionId) {
  loading.value = true
  try {
    const { data } = await api.get(`/contents/${props.contentId}/versions/${versionId}`)
    currentVersion.value = data
    selectedVersionId.value = versionId
    form.status = data.status
    form.highlights = flatten(data.payload)
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

async function loadAll() {
  loading.value = true
  try {
    const episodeRes = await api.get(`/episodes/${props.contentId}`)
    episode.value = episodeRes.data
    versions.value = episodeRes.data.versions || []
    const editable = versions.value.find((v) => v.status === 'draft' || v.status === 'reviewing')
    const target = editable || versions.value.find((v) => v.status === 'published') || versions.value[0]
    if (target) await loadVersion(target.id)
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    loading.value = false
  }
}

// ---------- 编辑操作 ----------
function addHighlight() {
  form.highlights.push({
    id: `candidate-${Date.now()}`,
    start_ms: 10000,
    end_ms: 15000,
    type: 'satisfying',
    intensity: 0.8,
    template: 'dual-button',
    title: '',
    effect: 'pulse',
    actions: [
      { key: 'shuang', label: '爽', tone: 'positive', icon: 'fire' },
      { key: 'shang-tou', label: '上头', tone: 'support', icon: 'boost' },
    ],
  })
}

async function removeHighlight(index) {
  try {
    await ElMessageBox.confirm('删除该高光点？', '确认删除', { type: 'warning' })
  } catch {
    return
  }
  form.highlights.splice(index, 1)
}

function addAction(h) {
  h.actions.push({ key: '', label: '', tone: 'positive', icon: 'heart' })
}
function removeAction(h, index) {
  h.actions.splice(index, 1)
}

async function save() {
  if (!currentVersion.value) return
  saving.value = true
  try {
    const { data } = await api.put(`/contents/${props.contentId}/versions/${selectedVersionId.value}`, {
      payload: buildPayload(),
      status: form.status,
    })
    ElMessage.success('已保存（含校验归一化）')
    currentVersion.value = data
    form.highlights = flatten(data.payload)
    await loadAll()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  } finally {
    saving.value = false
  }
}

async function publish() {
  try {
    await ElMessageBox.confirm(
      '发布后将立即生效到客户端 /api/contents/{id}/manifest，旧 published 版本将归档。确认发布？',
      '确认发布',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const { data } = await api.post(`/contents/${props.contentId}/versions/${selectedVersionId.value}/publish`)
    ElMessage.success(`已发布（${data.highlight_count} 个高光）`)
    await loadAll()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

async function createDraft() {
  try {
    const { data } = await api.post(`/contents/${props.contentId}/versions`, { source: 'manual' })
    ElMessage.success(`已创建草稿版本 #${data.id}`)
    await loadAll()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

async function rollback() {
  try {
    await ElMessageBox.confirm('将该历史版本重新发布（当前线上版本将归档）？', '确认回滚', { type: 'warning' })
  } catch {
    return
  }
  try {
    const { data } = await api.post(`/contents/${props.contentId}/versions/${selectedVersionId.value}/rollback`)
    ElMessage.success(`已回滚到版本 #${data.version_id}`)
    await loadAll()
  } catch (error) {
    ElMessage.error(errorDetail(error))
  }
}

const canEdit = computed(() => currentVersion.value && ['draft', 'reviewing'].includes(currentVersion.value.status))
const canPublish = computed(() => canEdit.value)
const canRollback = computed(() => currentVersion.value && ['published', 'archived'].includes(currentVersion.value.status))

// ---------- 时间轴 ----------
function markerStyle(h) {
  const total = durationSeconds.value
  if (!total) return { left: '0%', width: '0%' }
  const left = (h.start_ms / 1000 / total) * 100
  const width = Math.max(((h.end_ms - h.start_ms) / 1000 / total) * 100, 0.5)
  return { left: `${left}%`, width: `${width}%` }
}
const cursorStyle = computed(() => {
  const total = durationSeconds.value
  return { left: `${total ? (currentTime.value / total) * 100 : 0}%` }
})

onMounted(loadAll)
onBeforeUnmount(() => {
  videoRef.value?.pause()
})
</script>

<template>
  <div v-loading="loading">
    <div class="page-head">
      <h2>Manifest 编辑器 <span class="ep-title">{{ episode?.title }}</span></h2>
      <div>
        <el-button @click="router.push({ path: '/episodes', query: { drama_id: episode?.drama_id } })">返回剧集</el-button>
        <el-button type="primary" plain @click="createDraft">新建草稿</el-button>
        <el-button type="success" :disabled="!canPublish" @click="publish">发布</el-button>
        <el-button type="warning" :disabled="!canRollback" @click="rollback">回滚此版本</el-button>
        <el-button type="primary" :loading="saving" :disabled="!canEdit" @click="save">保存</el-button>
      </div>
    </div>

    <!-- 版本选择 -->
    <el-space wrap style="margin-bottom: 12px">
      <span class="field-label">版本：</span>
      <el-select v-model="selectedVersionId" style="width: 280px" @change="loadVersion">
        <el-option v-for="v in versions" :key="v.id" :value="v.id" :label="`#${v.id} ${v.source} · ${STATUS_MAP[v.status]?.label || v.status} · ${v.highlight_count} 高光`" />
      </el-select>
      <el-tag :type="STATUS_MAP[currentVersion?.status]?.type || 'info'" v-if="currentVersion">
        {{ STATUS_MAP[currentVersion.status]?.label || currentVersion.status }}
      </el-tag>
      <el-tag v-if="currentVersion" type="info" effect="plain">来源：{{ currentVersion.source }}</el-tag>
    </el-space>

    <el-row :gutter="16">
      <!-- 左：视频 + 时间轴 -->
      <el-col :span="13">
        <el-card shadow="never">
          <video
            ref="videoRef"
            :src="episode?.video_url"
            controls
            style="width: 100%; background: #000; border-radius: 6px"
            @loadedmetadata="meta"
            @timeupdate="tick"
          />
          <div class="timeline">
            <div
              v-for="(h, i) in form.highlights"
              :key="h.id || i"
              class="tl-marker"
              :style="markerStyle(h)"
              :title="`${h.title || h.id}: ${fmt(h.start_ms)} - ${fmt(h.end_ms)}`"
              @click="seek(h.start_ms)"
            />
            <div class="tl-cursor" :style="cursorStyle" />
          </div>
          <div class="timeline-caption">
            <span>当前 {{ fmt(currentTime * 1000) }}</span>
            <span>时长 {{ fmt(episode?.duration_ms || 0) }}</span>
          </div>
        </el-card>
      </el-col>

      <!-- 右：高光卡片列表 -->
      <el-col :span="11">
        <el-button size="small" type="primary" plain :disabled="!canEdit" @click="addHighlight" style="margin-bottom: 8px">
          + 新增高光
        </el-button>
        <div v-if="!form.highlights.length" class="empty-tip">暂无高光，点击"生成高光"或"新增高光"开始</div>
        <el-card
          v-for="(h, index) in form.highlights"
          :key="h.id || index"
          shadow="never"
          class="hl-card"
        >
          <template #header>
            <div class="hl-card-head">
              <span class="hl-index">高光 {{ index + 1 }}</span>
              <span class="hl-id">{{ h.id }}</span>
              <el-button size="small" type="danger" link :disabled="!canEdit" @click="removeHighlight(index)">删除</el-button>
            </div>
          </template>
          <el-form label-width="70px" size="small" :disabled="!canEdit">
            <el-row :gutter="8">
              <el-col :span="8">
                <el-form-item label="开始(ms)">
                  <el-input-number v-model="h.start_ms" :min="0" :step="500" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="结束(ms)">
                  <el-input-number v-model="h.end_ms" :min="0" :step="500" controls-position="right" style="width: 100%" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="定位">
                  <el-button size="small" @click="seek(h.start_ms)">播放 {{ fmt(h.start_ms) }}</el-button>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="8">
              <el-col :span="8">
                <el-form-item label="类型">
                  <el-select v-model="h.type" style="width: 100%">
                    <el-option v-for="t in HIGHLIGHT_TYPES" :key="t" :value="t" :label="t" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="模板">
                  <el-select v-model="h.template" style="width: 100%">
                    <el-option v-for="t in TEMPLATES" :key="t" :value="t" :label="t" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="特效">
                  <el-select v-model="h.effect" style="width: 100%">
                    <el-option v-for="e in EFFECTS" :key="e" :value="e" :label="e" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="强度">
              <el-slider v-model="h.intensity" :min="0" :max="1" :step="0.1" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="h.title" placeholder="如：身份曝光（≤12 字中文）" maxlength="12" show-word-limit />
            </el-form-item>
            <el-form-item label="互动选项">
              <div style="width: 100%">
                <div v-for="(a, ai) in h.actions" :key="ai" class="action-row">
                  <el-input v-model="a.key" placeholder="key" style="width: 110px" />
                  <el-input v-model="a.label" placeholder="文案" style="width: 90px" maxlength="6" />
                  <el-select v-model="a.tone" style="width: 110px">
                    <el-option v-for="t in TONES" :key="t" :value="t" :label="t" />
                  </el-select>
                  <el-select v-model="a.icon" style="width: 100px">
                    <el-option v-for="i in ICONS" :key="i" :value="i" :label="i" />
                  </el-select>
                  <el-button size="small" type="danger" link @click="removeAction(h, ai)">删</el-button>
                </div>
                <el-button size="small" link type="primary" @click="addAction(h)">+ 选项</el-button>
              </div>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-head h2 { margin: 0; }
.ep-title { color: #909399; font-size: 14px; font-weight: 400; }
.field-label { color: #606266; font-size: 14px; }
.timeline { position: relative; height: 26px; background: #f0f2f5; border-radius: 4px; margin-top: 10px; overflow: hidden; }
.tl-marker { position: absolute; top: 3px; bottom: 3px; background: #409eff; opacity: 0.55; border-radius: 2px; cursor: pointer; }
.tl-marker:hover { opacity: 0.9; }
.tl-cursor { position: absolute; top: 0; bottom: 0; width: 2px; background: #f56c6c; }
.timeline-caption { display: flex; justify-content: space-between; color: #909399; font-size: 12px; margin-top: 4px; }
.empty-tip { color: #909399; text-align: center; padding: 24px 0; }
.hl-card { margin-bottom: 10px; }
.hl-card-head { display: flex; align-items: center; gap: 8px; }
.hl-index { font-weight: 600; }
.hl-id { color: #909399; font-size: 12px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-row { display: flex; gap: 6px; margin-bottom: 6px; align-items: center; }
</style>
