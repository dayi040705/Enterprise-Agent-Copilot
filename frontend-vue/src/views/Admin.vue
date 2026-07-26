<template>
  <el-container style="height:100vh">
    <el-header style="background:#409eff;color:#fff;display:flex;align-items:center;gap:16px">
      <h3>管理后台</h3>
      <el-button @click="$router.push('/chat')" style="margin-left:auto">← 返回聊天</el-button>
    </el-header>

    <el-main>
      <el-tabs v-model="activeTab">
        <!-- Tab 1: 文档管理 -->
        <el-tab-pane label="文档管理" name="docs">
          <el-table :data="documents" border stripe>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="filename" label="文件名" />
            <el-table-column prop="department" label="部门" width="100" />
            <el-table-column prop="uploader" label="上传者" width="100" />
            <el-table-column prop="version" label="版本" width="70" />
            <el-table-column prop="chunk_count" label="块数" width="70" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status==='active'?'success':'info'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button v-if="row.status==='active'" size="small" type="warning"
                           @click="toggleDoc(row, 'disable')">禁用</el-button>
                <el-button v-else size="small" type="success"
                           @click="toggleDoc(row, 'enable')">启用</el-button>
                <el-button size="small" type="danger" @click="delDoc(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- Tab 2: 用户审批 -->
        <el-tab-pane label="用户审批" name="users">
          <el-table :data="pendingUsers" border stripe>
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="role" label="角色" width="100" />
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status==='active'?'success':'warning'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="250">
              <template #default="{ row }">
                <template v-if="row.status==='pending'">
                  <el-select v-model="departments[row.username]" placeholder="选择部门" size="small" style="width:120px">
                    <el-option label="HR" value="HR" />
                    <el-option label="TECH" value="TECH" />
                  </el-select>
                  <el-button size="small" type="primary"
                             @click="approve(row)" style="margin-left:8px">审批通过</el-button>
                </template>
                <span v-else style="color:#67c23a">已通过</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getDocuments, deleteDocument, disableDocument, enableDocument, getPendingUsers, approveUser } from '../api'

const router = useRouter()
const activeTab = ref('docs')
const documents = ref([])
const pendingUsers = ref([])
const departments = reactive({})

onMounted(async () => {
  if (!localStorage.getItem('token')) { router.push('/'); return }
  await loadData()
})

async function loadData() {
  try { const { data } = await getDocuments(); documents.value = data } catch (e) {}
  try { const { data } = await getPendingUsers(); pendingUsers.value = data } catch (e) {}
}

async function delDoc(row) {
  try {
    await ElMessageBox.confirm(`确定删除 "${row.filename}"？`, '确认', { type: 'warning' })
    await deleteDocument(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e) { /* 取消或失败 */ }
}

async function toggleDoc(row, action) {
  try {
    if (action === 'disable') await disableDocument(row.id)
    else await enableDocument(row.id)
    ElMessage.success('操作成功')
    loadData()
  } catch (e) { ElMessage.error('操作失败') }
}

async function approve(row) {
  if (!departments[row.username]) {
    ElMessage.warning('请先选择部门')
    return
  }
  try {
    await approveUser(row.username, departments[row.username])
    ElMessage.success(`${row.username} 审批通过`)
    loadData()
  } catch (e) { ElMessage.error('审批失败') }
}
</script>
