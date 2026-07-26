import axios from 'axios'

const api = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 60000,
})

// 自动带 token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401 自动跳回登录页
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/'
    }
    return Promise.reject(err)
  }
)

export default api

// ========== 认证 ==========
export const login = (username, password) =>
  api.post('/login', `username=${username}&password=${password}`, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
  })

// ========== 会话 ==========
export const createSession = () => api.post('/chat/session')

// ========== 聊天 (流式) ==========
export function chatStream(question, conversationId, token) {
  return fetch('http://127.0.0.1:8000/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({ question, conversation_id: conversationId || 'default' })
  })
}

// ========== 历史 ==========
export const getHistory = () => api.get('/chat/history')

// ========== 文档管理 ==========
export const getDocuments = () => api.get('/documents')
export const deleteDocument = (id) => api.delete(`/documents/${id}`)
export const disableDocument = (id) => api.patch(`/documents/${id}/disable`)
export const enableDocument = (id) => api.patch(`/documents/${id}/enable`)

// ========== 上传 ==========
export const uploadFile = (file, token) => {
  const form = new FormData()
  form.append('file', file)
  return fetch('http://127.0.0.1:8000/upload', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: form
  })
}

// ========== 管理员 ==========
export const getPendingUsers = () => api.get('/admin/pending-users')
export const approveUser = (username, department) =>
  api.put(`/admin/approve-user/${username}`, { department })
