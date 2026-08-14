export type Dataset = {
  id: string;
  project_id: string;
  filename: string;
  size_bytes: number;
  row_count: number | null;
  column_count: number | null;
  file_format: string;
  retention_status: string;
  source_channel: string;
  schema_columns: string[];
  created_at: string | null;
};

export type Project = {
  id: string;
  name: string;
  description: string | null;
  source_channel: string;
  created_at: string | null;
  datasets: Dataset[];
  experiment_ids: string[];
};

export type ModelRun = {
  id: string;
  model_name: string;
  status: string;
  metrics: Record<string, unknown>;
  fit_seconds: number | null;
  predict_seconds: number | null;
};

export type Experiment = {
  id: string;
  project_id: string;
  dataset_id: string;
  objective: string | null;
  target_column: string | null;
  task: string | null;
  primary_metric: string | null;
  winner_model: string | null;
  status: string;
  progress: number;
  error_message: string | null;
  source_channel: string;
  constitution: Record<string, unknown>;
  pending_clarification: Record<string, unknown> | null;
  result_summary: Record<string, unknown>;
  warnings: unknown[];
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  model_leaderboard: ModelRun[];
  reports: Array<{
    id: string;
    report_type: string;
    report_version: number;
    filename: string | null;
    content_type: string | null;
    size_bytes: number | null;
    sha256: string | null;
    evidence_hash: string | null;
    created_at: string | null;
  }>;
  audit_history: Array<{
    id: number;
    action: string;
    resource_type: string;
    metadata: Record<string, unknown>;
    created_at: string | null;
  }>;
};

export type DashboardOverview = {
  projects: Project[];
  experiments: Experiment[];
  summary: {
    project_count: number;
    dataset_count: number;
    experiment_count: number;
    statuses: Record<string, number>;
  };
};

export type TelegramLink = {
  linked: boolean;
  status: string;
  telegram_user?: string;
  linked_at?: string;
};
