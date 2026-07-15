<script lang="ts" setup>
import { onMounted, ref } from 'vue'
import { getAgentHandoffsAPI, getAgentSessionsAPI } from '@/apis/agent'
import type { AgentHandoffSummary, AgentSessionSummary } from '@/types/agent'

const sessions = ref<AgentSessionSummary[]>([])
const handoffs = ref<AgentHandoffSummary[]>([])
const backendAvailable = ref(true)

onMounted(async () => {
  try {
    ;[sessions.value, handoffs.value] = await Promise.all([
      getAgentSessionsAPI(),
      getAgentHandoffsAPI(),
    ])
  } catch {
    backendAvailable.value = false
  }
})
</script>

<template>
  <div class="app-container">
    <el-alert
      title="客服后台入口：使用管理员登录态，不会冒充会员调用聊天接口。"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="!backendAvailable"
      class="notice"
      title="Agent 管理端接口尚未部署，当前仅展示接入骨架。"
      type="warning"
      :closable="false"
    />

    <h3>最近会话</h3>
    <el-table :data="sessions" border>
      <el-table-column prop="session_id" label="会话编号" />
      <el-table-column prop="member_id" label="会员编号" />
      <el-table-column prop="intent" label="最近意图" />
      <el-table-column prop="handoff_required" label="需要转人工" />
    </el-table>

    <h3>转人工记录</h3>
    <el-table :data="handoffs" border>
      <el-table-column prop="session_id" label="会话编号" />
      <el-table-column prop="member_id" label="会员编号" />
      <el-table-column prop="reason" label="原因" />
    </el-table>
  </div>
</template>

<style scoped>
.notice,
h3 {
  margin-top: 20px;
}
</style>
