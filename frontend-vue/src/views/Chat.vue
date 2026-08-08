<template>
  <el-container style="height:100vh;background:#1a1a2e">
    <!-- 侧边栏 -->
    <el-aside width="260px" style="background:#16213e;color:#e0e0e0;display:flex;flex-direction:column;border-right:1px solid #0f3460">
      <div style="padding:16px;font-size:16px;font-weight:bold;border-bottom:1px solid #0f3460;color:#e94560">
        Enterprise Agent Copilot
      </div>
      <div style="padding:12px">
        <el-button type="primary" @click="newSession" style="width:100%">
          <el-icon><Plus /></el-icon> 新建会话
        </el-button>
      </div>
      <div style="padding:8px 12px;color:#aab;font-size:12px">历史会话</div>
      <div style="flex:1;overflow-y:auto;padding:0 8px">
        <div v-for="g in historyList" :key="g.conversation_id" @click="selectHistory(g)"
             :style="{padding:'8px 12px',margin:'2px 0',borderRadius:'6px',cursor:'pointer',
                      background: g.conversation_id===activeHistoryId ? '#409eff' : 'transparent', color: '#ccc',
                      fontSize:'13px'}">
          <div style="overflow:hidden;whiteSpace:'nowrap';textOverflow:'ellipsis'">{{ g.title?.slice(0, 25) }}</div>
          <div style="font-size:10px;color:#888;margin-top:2px">{{ g.records?.length || 0 }} 条对话</div>
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
    <el-main style="display:flex;flex-direction:column;padding:0;background:#1a1a2e">
      <div class="chat-header" style="background:#16213e;border-bottom:1px solid #0f3460;color:#e0e0e0;padding:12px 20px;display:flex;align-items:center;gap:12px">
        <span>会话: {{ conversationId?.slice(0, 8) || '未创建' }}...</span>
        <el-radio-group v-model="chatMode" size="small" style="margin-left:16px">
          <el-button type="success" size="small" @click="sendDailyBriefing" :disabled="sending" style="margin-right:4px">
            晨报
          </el-button>
          <el-button type="warning" size="small" @click="sendListingDiagnosis" :disabled="sending" style="margin-right:8px">
            Listing诊断
          </el-button>
          <el-radio-button value="unified">Unified</el-radio-button>
          <el-radio-button value="rag">RAG</el-radio-button>
          <el-radio-button value="agent">Agent</el-radio-button>
          <el-radio-button value="planner">Planner</el-radio-button>
          <el-radio-button value="multi">Multi</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="uploadRef.click()" :icon="Upload" style="margin-left:auto">
          上传文档
        </el-button>
        <input ref="uploadRef" type="file" accept=".pdf,.docx,.md,.txt" style="display:none" @change="handleUpload" />
      </div>

      <div class="chat-messages" ref="msgContainer">
        <div v-if="messages.length===0" style="text-align:center;color:#555;margin-top:200px">
          <el-icon :size="48" color="#555"><ChatDotRound /></el-icon>
          <p style="margin-top:16px;color:#666">输入问题，开始对话</p>
        </div>

        <div v-for="(msg, i) in messages" :key="i"
             :class="['msg-bubble', msg.role==='user' ? 'msg-user' : 'msg-assistant']">
          <div class="msg-role">{{ msg.role === 'user' ? username : (chatMode === 'rag' ? 'AI 助手' : chatMode === 'agent' ? 'Agent' : 'Planner') }}</div>
          <!-- Planner 计划 -->
          <div v-if="msg.plan?.length" class="plan-box">
            <div class="plan-title">执行计划</div>
            <div v-for="(s, j) in msg.plan" :key="j" class="plan-step">{{ j+1 }}. {{ s }}</div>
          </div>
          <!-- Agent 工具调用卡片 — 可折叠 -->
          <div v-if="msg.toolCalls?.length" class="tool-calls" style="margin:8px 0">
            <details style="background:#252547;border-radius:8px;padding:8px 12px;font-size:12px">
              <summary style="cursor:pointer;color:#7ec8e3;font-weight:500">
                TOOLS ({{ msg.toolCalls.length }})
              </summary>
              <div v-for="(tc, j) in msg.toolCalls" :key="j"
                   style="margin-top:6px;padding:6px 8px;background:#1a1a3e;border-radius:4px;border-left:3px solid #e94560">
                <span style="color:#e94560;font-weight:600">{{ tc.tool }}</span>
                <span style="color:#aaa;margin-left:8px">{{ JSON.stringify(tc.args).slice(0, 100) }}</span>
                <div v-if="tc.result" style="color:#7ec8e3;margin-top:4px;max-height:60px;overflow:hidden">
                  {{ tc.result?.slice(0, 120) }}
                </div>
              </div>
            </details>
          </div>
          <div class="msg-text">{{ msg.content }}</div>
          <div v-if="msg.traceLink" style="margin-top:6px">
            <el-button size="small" type="success" @click="$router.push(msg.traceLink)">查看 Trace</el-button>
          </div>
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
import { getHistory, createSession, chatStream, agentStream, plannerStream, multiAgentStream, unifiedStream, dailyBriefing, listingDiagnosis, uploadFile } from '../api'

const router = useRouter()
const username = ref(localStorage.getItem('username') || '用户')
const isAdmin = ref(localStorage.getItem('username') === 'admin')
const chatMode = ref('unified')  // 'unified' | 'rag' | 'agent' | 'planner' | 'multi'
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
    // 按 conversation_id 分组, 每组显示第一条问题作为标题
    const groups = {}
    for (const r of data) {
      if (!groups[r.conversation_id]) {
        groups[r.conversation_id] = { conversation_id: r.conversation_id, title: r.question, records: [] }
      }
      groups[r.conversation_id].records.push(r)
    }
    historyList.value = Object.values(groups)
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

async function selectHistory(group) {
  activeHistoryId.value = group.conversation_id
  conversationId.value = group.conversation_id
  messages.value = []
  for (const r of group.records) {
    messages.value.push({ role: 'user', content: r.question })
    const meta = parseMeta(r.trace_data)
    const content = r.answer + (meta.session_id ? '\n\n[Session: ' + meta.session_id + ']' : '')
    messages.value.push({ role: 'assistant', content, sources: parseSources(r.sources),
                          mode: meta.mode, sessionId: meta.session_id })
  }
}

function parseMeta(metaJson) {
  try { return JSON.parse(metaJson) || {} } catch { return {} }
}

function parseSources(sourcesJson) {
  try { return JSON.parse(sourcesJson) || [] } catch { return [] }
}

async function sendMessage() {
  const q = question.value.trim()
  if (!q || sending.value) return
  question.value = ''

  messages.value.push({ role: 'user', content: q })

  // 按模式分发
  if (chatMode.value === 'unified') {
    await sendUnifiedMessage(q)
  } else if (chatMode.value === 'agent') {
    await sendAgentMessage(q)
  } else if (chatMode.value === 'planner') {
    await sendPlannerMessage(q)
  } else if (chatMode.value === 'multi') {
    await sendMultiAgentMessage(q)
  } else {
    await sendRagMessage(q)
  }

  sending.value = false
  await loadHistory()
}

async function sendRagMessage(q) {
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
        } catch (e) {}
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }
}

async function sendAgentMessage(q) {
  sending.value = true

  // Agent 模式下, 工具调用显示为独立消息
  const toolMsgs = []  // 收集工具调用消息
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [], toolCalls: [] })
  messages.value.push(assistantMsg)

  try {
    const resp = await agentStream(q, conversationId.value, localStorage.getItem('token'))
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
          if (event.type === 'tool_call') {
            // 在回答中插入工具调用卡片
            const toolInfo = { tool: event.tool, args: event.args, result: '' }
            assistantMsg.toolCalls.push(toolInfo)
            assistantMsg.content += `\n\n[调用工具: ${event.tool}(${JSON.stringify(event.args)})]`
          } else if (event.type === 'tool_result') {
            // 更新最后一个工具调用的结果
            const last = assistantMsg.toolCalls[assistantMsg.toolCalls.length - 1]
            if (last) last.result = event.data?.slice(0, 100) || ''
            assistantMsg.content += `\n[结果: ${(event.data || '').slice(0, 80)}...]`
          } else if (event.type === 'status') {
            // 状态更新, 不显示
          } else if (event.type === 'done') {
            assistantMsg.content = event.answer || assistantMsg.content
          }
          await nextTick()
          scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }
}

async function sendPlannerMessage(q) {
  sending.value = true
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [], toolCalls: [], plan: [] })
  messages.value.push(assistantMsg)

  try {
    const resp = await plannerStream(q, conversationId.value, localStorage.getItem('token'))
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
          if (event.type === 'plan') {
            assistantMsg.plan = event.data || []
            assistantMsg.content = '执行计划:\n' + event.data.map((s, i) => `  ${i+1}. ${s}`).join('\n')
          } else if (event.type === 'tool_start') {
            assistantMsg.toolCalls.push({ tool: event.tool, args: event.args, result: '执行中...' })
          } else if (event.type === 'tool_result') {
            const last = assistantMsg.toolCalls[assistantMsg.toolCalls.length - 1]
            if (last) last.result = (event.data || '').slice(0, 120)
          } else if (event.type === 'token') {
            // 逐 token 追加到答案 (清除计划文本, 开始流式回答)
            if (assistantMsg.content && assistantMsg.content.startsWith('执行计划')) {
              assistantMsg.content = ''
            }
            assistantMsg.content += event.data
          } else if (event.type === 'done') {
            assistantMsg.content = event.answer || assistantMsg.content
            if (event.plan) assistantMsg.plan = event.plan
          }
          await nextTick()
          scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }
}

async function sendDailyBriefing() {
  sending.value = true
  const assistantMsg = reactive({ role: 'assistant', content: '', toolCalls: [], plan: [], sessionId: '' })
  messages.value.push(assistantMsg)
  try {
    const resp = await dailyBriefing(localStorage.getItem('token'))
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
          if (event.type === 'status') assistantMsg.content += '[' + event.data + ']\n'
          else if (event.type === 'plan') assistantMsg.plan = event.data || []
          else if (event.type === 'tool_call' || event.type === 'tool_start') assistantMsg.toolCalls.push({ tool: event.tool, args: event.args, result: '...' })
          else if (event.type === 'token') { assistantMsg.content += event.data; await nextTick(); scrollBottom() }
          else if (event.type === 'done') { assistantMsg.content = event.answer || assistantMsg.content; assistantMsg.sessionId = event.session_id || '' }
          await nextTick(); scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) { assistantMsg.content = '日报请求失败: ' + e.message }
  sending.value = false
}

async function sendListingDiagnosis() {
  const sku = question.value.trim() || '51a41e5b'
  if (sku === question.value.trim()) question.value = ''
  sending.value = true
  const assistantMsg = reactive({ role: 'assistant', content: '', toolCalls: [], plan: [], sessionId: '' })
  messages.value.push({ role: 'user', content: '诊断 SKU: ' + sku })
  messages.value.push(assistantMsg)
  try {
    const resp = await listingDiagnosis(sku, localStorage.getItem('token'))
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
          if (event.type === 'status') assistantMsg.content += '[' + event.data + ']\n'
          else if (event.type === 'plan') assistantMsg.plan = event.data || []
          else if (event.type === 'tool_call' || event.type === 'tool_start') assistantMsg.toolCalls.push({ tool: event.tool, args: event.args, result: '...' })
          else if (event.type === 'token') { assistantMsg.content += event.data; await nextTick(); scrollBottom() }
          else if (event.type === 'done') { assistantMsg.content = event.answer || assistantMsg.content; assistantMsg.sessionId = event.session_id || '' }
          await nextTick(); scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) { assistantMsg.content = '诊断请求失败: ' + e.message }
  sending.value = false
}

async function sendUnifiedMessage(q) {
  sending.value = true
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [], toolCalls: [], plan: [], sessionId: '' })
  messages.value.push(assistantMsg)

  try {
    const resp = await unifiedStream(q, conversationId.value, localStorage.getItem('token'))
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
          if (event.type === 'route') {
            assistantMsg.content = 'Router: ' + event.mode + ' 模式\n\n'
          } else if (event.type === 'plan') {
            assistantMsg.plan = event.data || []
            assistantMsg.content += 'Supervisor 拆解任务:\n' + event.data.map((s, i) => '  ' + (i+1) + '. ' + s).join('\n')
          } else if (event.type === 'tool_call' || event.type === 'tool_start') {
            assistantMsg.toolCalls.push({ tool: event.tool, args: event.args, result: '执行中...' })
          } else if (event.type === 'tool_result') {
            const last = assistantMsg.toolCalls[assistantMsg.toolCalls.length - 1]
            if (last) last.result = (event.data || '').slice(0, 120)
          } else if (event.type === 'token') {
            if (assistantMsg.content && assistantMsg.content.startsWith('Router:')) assistantMsg.content = ''
            assistantMsg.content += event.data
            await nextTick(); scrollBottom()
          } else if (event.type === 'status') {
            assistantMsg.content += '\n[' + event.data + ']'
          } else if (event.type === 'done') {
            assistantMsg.content = event.answer || assistantMsg.content
            assistantMsg.sessionId = event.session_id || ''
            if (event.session_id) assistantMsg.traceLink = '/trace/' + event.session_id
          }
          await nextTick(); scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }
  sending.value = false
}

async function sendMultiAgentMessage(q) {
  sending.value = true
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [], toolCalls: [], plan: [], sessionId: '' })
  messages.value.push(assistantMsg)

  try {
    const resp = await multiAgentStream(q, conversationId.value, localStorage.getItem('token'))
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
          if (event.type === 'plan') {
            assistantMsg.plan = event.data || []
            assistantMsg.content = 'Multi-Agent 协作:\n' + event.data.map((s, i) => `  ${i+1}. ${s}`).join('\n')
          } else if (event.type === 'token') {
            // 流式逐 token 显示 Reporter 生成的报告
            if (assistantMsg.content && assistantMsg.content.startsWith('Supervisor')) {
              assistantMsg.content = ''  // 清掉计划文字, 开始流式报告
            }
            assistantMsg.content += event.data
            await nextTick()
            scrollBottom()
          } else if (event.type === 'status') {
            assistantMsg.content += '\n[' + event.data + ']'
          } else if (event.type === 'done') {
            assistantMsg.content = event.answer || assistantMsg.content
            assistantMsg.sessionId = event.session_id || ''
            if (event.session_id) {
              assistantMsg.content += '\n\n[Session: ' + event.session_id + ']'
              assistantMsg.traceLink = '/trace/' + event.session_id
            }
            if (event.review) {
              assistantMsg.content += '\n[Reviewer: faith=' +
                Math.round((event.review.faithfulness||0)*100) + '%]'
            }
          }
          await nextTick()
          scrollBottom()
        } catch (e) {}
      }
    }
  } catch (e) {
    assistantMsg.content = '请求失败: ' + e.message
  }
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
/* Agent 工具调用卡片 */
.tool-calls { margin: 8px 0; display: flex; flex-direction: column; gap: 4px; }
.tool-card { background: #f0f5ff; border: 1px solid #d0e0ff; border-radius: 6px; padding: 4px 10px; font-size: 12px; display: flex; align-items: center; gap: 6px; }
.tool-badge { background: #e94560; color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: bold; }
.tool-name { color: #409eff; font-weight: bold; }
.tool-args { color: #999; font-family: monospace; }
/* Planner 计划卡片 */
.plan-box { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 10px 14px; margin: 6px 0; }
.plan-title { color: #16a34a; font-size: 13px; font-weight: bold; margin-bottom: 4px; }
.plan-step { color: #333; font-size: 12px; line-height: 1.8; }
</style>
