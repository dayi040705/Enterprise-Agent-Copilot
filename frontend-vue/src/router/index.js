import { createRouter, createWebHistory } from 'vue-router'
import Login from '../views/Login.vue'
import Chat from '../views/Chat.vue'
import Admin from '../views/Admin.vue'
import Trace from '../views/Trace.vue'

const routes = [
  { path: '/', name: 'Login', component: Login },
  { path: '/chat', name: 'Chat', component: Chat },
  { path: '/admin', name: 'Admin', component: Admin },
  { path: '/trace/:id?', name: 'Trace', component: Trace },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
