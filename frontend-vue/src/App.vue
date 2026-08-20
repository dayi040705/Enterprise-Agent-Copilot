<template>
  <!-- keep-alive: 跳转到 Trace/Admin 页时保持 Chat 组件状态 (会话/消息不丢失) -->
  <router-view v-slot="{ Component }">
    <keep-alive include="Chat">
      <component :is="Component" />
    </keep-alive>
  </router-view>
</template>

<script setup>
// 根组件 — 路由驱动, 无额外布局
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, 'Microsoft YaHei', sans-serif; background: #f0f2f5; }
#app { height: 100vh; }
</style>
