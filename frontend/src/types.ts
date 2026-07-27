// Зеркала Pydantic-схем бэкенда (backend/app/schemas/{research,run,extraction}.py)

export type SessionStatus = 'active' | 'running_tools' | 'comparing' | 'completed' | 'failed';

export interface SessionMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  created_at: string;
}

export interface ExcludedSite {
  start_url: string;
  reason: string;
}

export interface Winner {
  run_id: string;
  start_url: string;
  label: string;
  reason: string;
}

export interface Ranking {
  run_id: string;
  url: string;
  score: number;
  summary: string;
}

export interface Dimension {
  name: string;
  scores: Record<string, number | string>;
}

export interface ComparisonResult {
  session_id: string;
  comparison_task: string;
  rubric: string;
  status: 'completed' | 'partial' | 'failed';
  excluded: ExcludedSite[];
  winner: Winner | null;
  rankings: Ranking[];
  dimensions: Dimension[];
  narrative: string;
  generated_at: string;
}

export interface SessionRecord {
  id: string;
  title: string;
  status: SessionStatus;
  research_intent: string | null;
  messages: SessionMessage[];
  run_ids: string[];
  comparison_result: ComparisonResult | null;
  created_at: string;
  finished_at: string | null;
}

export interface SessionListItem {
  session_id: string;
  title: string;
  status: SessionStatus;
  runs: number;
  created_at: string;
}

export interface CrawlStep {
  index: number;
  state: string;
  url: string;
  action: string;
  target_url: string | null;
  reasoning: string;
  note: string;
  duration_ms: number;
  screenshot_paths: Record<string, string>;
}

export interface Evidence {
  url: string;
  quote: string;
  source: string;
}

export interface Fact {
  key: string;
  label: string;
  value: string;
  confidence: string;
  evidence: Evidence[];
}

export interface ExtractionResult {
  summary: string;
  status: string;
  facts: Fact[];
  not_found: { key: string; reason: string }[];
  article: { url: string; title: string; word_count: number } | null;
  design_tokens: Record<string, unknown>;
  pages_visited: number;
  duration_seconds: number;
}

export interface RunRecord {
  id: string;
  config: { start_url: string; task: string; max_pages: number };
  status: string;
  session_id: string | null;
  intent: string;
  pages_visited: number;
  current_url: string;
  steps: CrawlStep[];
  result: ExtractionResult | null;
  error_message: string;
  started_at: string;
  finished_at: string | null;
}

// SSE-события (doc 15 v0.6)
export interface CrawlProgress {
  run_id: string;
  status: string;
  start_url: string;
  pages_visited: number;
  max_pages: number;
  current_url: string;
}

export interface SseMessage {
  index: number;
  role: SessionMessage['role'];
  content: string;
  created_at: string;
}

export interface ChallengeWait {
  run_id: string;
  start_url: string;
  url: string;
  kind: string;
  action?: string | null; // confirm_submit / handoff (Tier 2/3): что подготовлено
}
