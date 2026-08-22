import axios from 'axios'

// 管理端 API 客户端：统一附加 Bearer ADMIN_TOKEN 与 X-Admin-Operator（审计操作者）。
const api = axios.create({ baseURL: '/admin/api' })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token')
  const operator = localStorage.getItem('admin_operator') || 'admin'
  if (token) config.headers.Authorization = `Bearer ${token}`
  config.headers['X-Admin-Operator'] = operator
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    if (status === 401) {
      localStorage.removeItem('admin_token')
      if (location.hash !== '#/login') location.hash = '#/login'
    }
    return Promise.reject(error)
  },
)

export function errorDetail(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) {
    const reasons = Array.isArray(detail.reasons) ? detail.reasons : []
    return reasons.length ? `${detail.message}: ${reasons.join('；')}` : detail.message
  }
  return error.message || '请求失败'
}

export default api
