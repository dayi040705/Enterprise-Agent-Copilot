<template>
  <el-container style="height:100vh">
    <el-header style="background:#1a1a2e;color:#fff;display:flex;align-items:center;gap:16px">
      <h3>Agent Execution Trace</h3>
      <el-input v-model="sessionId" placeholder="Session ID" style="width:200px" size="small" />
      <el-button size="small" type="primary" @click="loadTrace">加载</el-button>
      <el-button @click="$router.push('/chat')" style="margin-left:auto">返回聊天</el-button>
    </el-header>

    <el-main style="background:#f5f7fa;overflow:auto;padding:20px">
      <div v-if="!root" style="text-align:center;margin-top:200px;color:#999">
        输入 Session ID 查看 Agent 执行轨迹
      </div>

      <div v-else class="trace-tree">
        <TraceNode :node="root" :depth="0" :expanded="true" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, defineComponent, h, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()
const sessionId = ref(route.params.id || '')
const root = ref(null)

onMounted(() => { if (sessionId.value) loadTrace() })

async function loadTrace() {
  try {
    const { data } = await api.get(`/chat/trace/${sessionId.value}`)
    root.value = data
  } catch (e) {
    ElMessage.error('加载失败: session 不存在或已过期')
  }
}

// 递归 Trace 节点组件
const TraceNode = defineComponent({
  name: 'TraceNode',
  props: { node: Object, depth: Number, expanded: { type: Boolean, default: true } },
  setup(props) {
    const isExpanded = ref(props.expanded)
    const toggle = () => { isExpanded.value = !isExpanded.value }

    const typeColors = {
      user: '#409eff', supervisor: '#e6a23c', agent: '#67c23a',
      tool: '#e94560', reporter: '#909399', reviewer: '#f56c6c'
    }
    const typeLabels = {
      user: 'USER', supervisor: 'SUP', agent: 'AGENT',
      tool: 'TOOL', reporter: 'REPORT', reviewer: 'REVIEW'
    }
    const color = typeColors[props.node.type] || '#999'
    const label = typeLabels[props.node.type] || props.node.type?.toUpperCase()

    return () => {
      const n = props.node
      if (!n) return null
      const hasChildren = n.children?.length > 0
      const indent = props.depth * 24

      return h('div', { style: { marginLeft: indent + 'px' } }, [
        // 节点行
        h('div', {
          onClick: toggle,
          style: { display: 'flex', alignItems: 'center', padding: '4px 0', cursor: hasChildren ? 'pointer' : 'default',
                   borderLeft: props.depth > 0 ? '2px solid #e0e0e0' : 'none', paddingLeft: '12px' }
        }, [
          hasChildren ? h('span', { style: { marginRight: 6, fontSize: 10 } },
                           isExpanded.value ? '▼' : '▶') : h('span', { style: { width: 12, display: 'inline-block' } }),
          h('span', { style: { background: color, color: '#fff', padding: '2px 6px', borderRadius: 3,
                               fontSize: 10, fontWeight: 'bold', marginRight: 8, minWidth: 50, textAlign: 'center' } },
            label),
          h('span', { style: { fontWeight: 'bold', fontSize: 14 } }, n.name || n.id),
          n.timestamp ? h('span', { style: { marginLeft: 12, color: '#999', fontSize: 11 } }, n.timestamp) : null,
        ]),

        // 展开时显示详情 + 子节点
        isExpanded.value ? [
          // 详情卡片
          (n.input || n.output) ? h('div', { style: { background: '#fff', border: '1px solid #eee',
                   borderRadius: 6, padding: 8, margin: '4px 0 8px 24px', fontSize: 12, maxWidth: 600 } }, [
            n.input ? h('div', { style: { marginBottom: 4 } },
                         [h('span', { style: { color: '#999' } }, 'Input: '),
                          h('span', {}, typeof n.input === 'string' ? n.input.slice(0, 200) : JSON.stringify(n.input).slice(0, 200))]) : null,
            n.output ? h('div', {}, [h('span', { style: { color: '#999' } }, 'Output: '),
                          h('span', {}, typeof n.output === 'string' ? n.output.slice(0, 300) : JSON.stringify(n.output).slice(0, 300))]) : null,
          ]) : null,
          // 子节点
          ...(hasChildren ? n.children.map(child =>
            h(TraceNode, { node: child, depth: props.depth + 1, expanded: true })
          ) : [])
        ] : []
      ])
    }
  }
})
</script>

<style scoped>
.trace-tree { font-family: 'Menlo', 'Consolas', monospace; padding: 16px; }
</style>
