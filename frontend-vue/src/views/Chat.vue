<template>
  <el-container style="height:100vh">
    <!-- 侧边栏 -->
    <el-aside width="260px" style="background:#304156;color:#fff;display:flex;flex-direction:column">
      <div style="padding:16px;font-size:16px;font-weight:bold;border-bottom:1px solid #4a5a6a">
        📚 RAG 知识库
      </div>
      <div style="padding:12px">
        <el-button type="primary" @click="newSession" style="width:100%">
          <el-icon><Plus /></el-icon> 新建会话
        </el-button>
      </div>
      <div style="padding:8px 12px;color:#aab;font-size:12px">历史会话</div>
      <div style="flex:1;overflow-y:auto;padding:0 8px">
        <div v-for="h in historyList" :key="h.id" @click="selectHistory(h)"
             :style="{padding:'8px 12px',margin:'2px 0',borderRadius:'6px',cursor:'pointer',
                      background: h.id===activeHistoryId ? '#409eff' : 'transparent', color: '#ccc',
                      fontSize:'13px', overflow:'hidden', whiteSpace:'nowrap', textOverflow:'ellipsis'}">
          {{ h.question?.slice(0, 30) }}
        </div>
        <div v-if="!historyList.length" style="color:#666;font-size:12px;padding:12px;text-align:center">
          暂无历史记录
        </div>
      </div>
      <div style="padding:12px;border-top:1px solid #4a5a6a;font-size:12px;color:#aab">
        {{ username }} |
        <el-button v-if="isAdmin" link size="small" @click="$router.push('/admin')" style="color:#67c23a">
          管理后台
        </el-button>
        <el-button link size="small" @click="logout" style="color:#f56c6c">退出</el-button>
      </div>
    </el-aside>

    <!-- 聊天区 -->
    <el-main style="display:flex;flex-direction:column;padding:0;background:#f5f7fa">
      <div class="chat-header">
        <span>会话: {{ conversationId?.slice(0, 8) || '未创建' }}...</span>
        <el-button size="small" @click="uploadRef.click()" :icon="Upload" style="margin-left:auto">
          上传文档
        </el-button>
        <input ref="uploadRef" type="file" accept=".pdf,.docx,.md,.txt" style="display:none" @change="handleUpload" />
      </div>

      <div class="chat-messages" ref="msgContainer">
        <div v-if="messages.length===0" style="text-align:center;color:#999;margin-top:200px">
          <el-icon :size="48"><ChatDotRound /></el-icon>
          <p style="margin-top:16px">输入问题，开始对话</p>
        </div>

        <div v-for="(msg, i) in messages" :key="i"
             :class="['msg-bubble', msg.role==='user' ? 'msg-user' : 'msg-assistant']">
          <div class="msg-role">{{ msg.role === 'user' ? username : 'AI 助手' }}</div>
          <div class="msg-text">{{ msg.content }}</div>
          <div v-if="msg.sources?.length" class="msg-sources">
            引用: <el-tag v-for="s in msg.sources" :key="s.source" size="small" type="info" style="margin:2px">
              {{ s.source }} (P{{ s.page }})
            </el-tag>
          </div>
        </div>
      </div>

      <div class="chat-input">
        <el-input v-model="question" placeholder="输入问题, Enter 发送..." size="large"
                  @keydown.enter="sendMessage" :disabled="sending">
          <template #append>
            <el-button @click="sendMessage" :loading="sending" :icon="Promotion" type="primary">
              发送
            </el-button>
          </template>
        </el-input>
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Promotion, Upload, ChatDotRound } from '@element-plus/icons-vue'
import { getHistory, createSession, chatStream, uploadFile } from '../api'

const router = useRouter()
const username = ref(localStorage.getItem('username') || '用户')
const isAdmin = ref(localStorage.getItem('username') === 'admin')
const question = ref('')
const sending = ref(false)
const conversationId = ref('')
const activeHistoryId = ref(null)
const historyList = ref([])
const messages = ref([])
const msgContainer = ref(null)
const uploadRef = ref(null)

onMounted(async () => {
  if (!localStorage.getItem('token')) { router.push('/'); return }
  await loadHistory()
  await newSession()
})

async function loadHistory() {
  try {
    const { data } = await getHistory()
    historyList.value = data
  } catch (e) { /* 忽略 */ }
}

async function newSession() {
  try {
    const { data } = await createSession()
    conversationId.value = data.conversation_id
    messages.value = []
    activeHistoryId.value = null
  } catch (e) { ElMessage.error('创建会话失败') }
}

function selectHistory(h) {
  activeHistoryId.value = h.id
  conversationId.value = h.conversation_id
}

async function sendMessage() {
  const q = question.value.trim()
  if (!q || sending.value) return
  question.value = ''

  messages.value.push({ role: 'user', content: q })
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [] })
  messages.value.push(assistantMsg)
  sending.value = true

  try {
    const resp = await chatStream(q, conversationId.value, localStorage.getItem('token'))
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const dataLine = line.startsWith('data: ') ? line.slice(6).trim() : ''
        if (!dataLine) continue
        try {
          const event = JSON.parse(dataLine)
          if (event.type === 'token') {
            assistantMsg.content += event.data
            await nextTick()
            scrollBottom()
          } else if (event.type === 'done' && event.sources) {
            assistantMsg.sources = event.sources
          }
        } catch (e) { /* skip bad JSON */ }
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }

  sending.value = false
  await loadHistory()
}

function scrollBottom() {
  if (msgContainer.value) {
    msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  }
}

async function handleUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  try {
    await uploadFile(file, localStorage.getItem('token'))
    ElMessage.success(`上传成功: ${file.name}`)
  } catch (e) {
    ElMessage.error('上传失败')
  }
}

function logout() {
  localStorage.clear()
  router.push('/')
}
</script>

<style scoped>
.chat-header {
  padding: 12px 20px; background: #fff; border-bottom: 1px solid #e4e7ed;
  display: flex; align-items: center; font-size: 14px; color: #666;
}
.chat-messages {
  flex: 1; overflow-y: auto; padding: 20px;
  display: flex; flex-direction: column; gap: 16px;
}
.chat-input { padding: 16px 20px; background: #fff; border-top: 1px solid #e4e7ed; }
.msg-bubble { max-width: 80%; padding: 12px 16px; border-radius: 12px; }
.msg-user { align-self: flex-end; background: #409eff; color: #fff; }
.msg-assistant { align-self: flex-start; background: #fff; border: 1px solid #e4e7ed; }
.msg-role { font-size: 12px; margin-bottom: 4px; opacity: 0.7; }
.msg-text { font-size: 15px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.msg-sources { margin-top: 10px; padding-top: 8px; border-top: 1px solid #eee; }
</style>
