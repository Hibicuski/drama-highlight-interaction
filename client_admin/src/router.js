import { createRouter, createWebHashHistory } from 'vue-router'

import Login from './views/Login.vue'
import Dramas from './views/Dramas.vue'
import Episodes from './views/Episodes.vue'
import ManifestEditor from './views/ManifestEditor.vue'
import GenerationTasks from './views/GenerationTasks.vue'
import AuditLogs from './views/AuditLogs.vue'

// hash 路由：生产环境由 FastAPI 静态挂载 /admin，无需 SPA 回退配置。
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: Login },
    { path: '/', redirect: '/dramas' },
    { path: '/dramas', component: Dramas },
    { path: '/episodes', component: Episodes, props: (route) => ({ dramaId: Number(route.query.drama_id) }) },
    { path: '/editor/:contentId', component: ManifestEditor, props: true },
    { path: '/tasks', component: GenerationTasks },
    { path: '/audit', component: AuditLogs },
  ],
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !localStorage.getItem('admin_token')) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
