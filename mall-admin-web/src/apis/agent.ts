import axios from 'axios'
import { useUserStore } from '@/stores/user'
import type { AgentHandoffSummary, AgentSessionSummary } from '@/types/agent'

const agentAdminHttp = axios.create({
  baseURL: import.meta.env.VITE_AGENT_API_BASE_URL || '/agent-api',
  timeout: 5000,
})

agentAdminHttp.interceptors.request.use(config => {
  const token = useUserStore().userInfo.token
  if (token) config.headers.Authorization = token
  return config
})

export async function getAgentSessionsAPI(): Promise<AgentSessionSummary[]> {
  const response = await agentAdminHttp.get<AgentSessionSummary[]>('/agent-admin/sessions')
  return response.data
}

export async function getAgentHandoffsAPI(): Promise<AgentHandoffSummary[]> {
  const response = await agentAdminHttp.get<AgentHandoffSummary[]>('/agent-admin/handoffs')
  return response.data
}
