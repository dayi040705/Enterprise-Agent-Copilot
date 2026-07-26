import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Chat from '../views/Chat.vue'
import Admin from '../views/Admin.vue'

const routes = [
  { path: '/', name: 'Login', component: Login },
  { path: '/chat', name: 'Chat', component: Chat },
  { path: '/admin', name: 'Admin', component: Admin },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
