<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header>
        <h2 style="text-align:center; color:#409eff">企业知识库 RAG 助手</h2>
      </template>
      <el-form :model="form" label-width="80px" @submit.prevent="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading" style="width:100%">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <p style="text-align:center;color:#999;font-size:12px">
        测试账号: zhangsan / 123456 (HR) | admin / 123456 (管理员)
      </p>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: 'zhangsan', password: '123456' })

async function handleLogin() {
  loading.value = true
  try {
    const { data } = await login(form.username, form.password)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('username', form.username)
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 400px;
}
</style>
