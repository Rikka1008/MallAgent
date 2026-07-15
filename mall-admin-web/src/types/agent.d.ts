export interface AgentSessionSummary {
  session_id: string
  member_id: string
  intent?: string
  handoff_required: boolean
  updated_at?: string
}

export interface AgentHandoffSummary {
  session_id: string
  member_id: string
  reason: string
  created_at?: string
}
