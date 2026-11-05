export type Role = "user" | "assistant";

export interface Msg { 
  role: Role; 
  content: string; 
}

export interface Step { 
  label: string; 
  detail?: any; 
  ts?: string;
}

export interface InterruptPayload {
  kind: "action" | "draft";
  action?: { tool: string; 
  args: Record<string, any> };
  reasons?: string[];
  policy_ref?: string | null;
  draft?: string;
  confidence?: number;
  sentiment?: string;
  revisions?: number;
}

export interface ThreadSummary {
  thread_id: string; 
  title: string | null; 
  customer_id: string | null; 
  updated_at: string;
}

export interface ThreadDetail {
  thread: ThreadSummary; 
  messages: Msg[]; 
  events: any[]; 
  pending_interrupt: InterruptPayload | null;
  status: string; 
  final_reply: string | null; 
  intent?: string; 
  confidence?: number;
}

export interface Checkpoint { 
  checkpoint_id: string; 
  ts?: string; 
  step?: number;
}

export interface Stats {
  threads: number; 
  refunds: number; 
  escalations: number; 
  feedback_up: number; 
  feedback_down: number;
}

export interface Customer { 
  id: string; 
  name: string; 
  email: string; 
  tier: string; 
  status: string;
}

export interface SSEEvent { 
  event: string; 
  data: any;
}

export interface ChatBody {
  thread_id: string | null;
  customer_id: string;
  message: string;
}

export interface ApproveBody {
  approved: boolean;
  feedback: string;
}

export type StreamRequestBody = ChatBody | ApproveBody;