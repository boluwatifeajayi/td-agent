export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Provider = "gemini" | "claude";

export interface RepoSummary {
  name: string;
  latest_score: number;
  issue_count: number;
  last_analysed: string;
  model: string;
  provider: Provider | "unknown";
  commit_count: number;
}

export interface JobStatus {
  status: "pending" | "running" | "done" | "failed";
  progress: { current: number; total: number; stage: string };
  result_id: string | null;
  error: string | null;
  repo_name: string;
  mode: "latest" | "history";
  provider: Provider;
}

export interface Issue {
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  confidence?: "low" | "medium" | "high";
  remediation_minutes: number;
  description: string;
  location: string;
  suggestion: string;
  why_debt?: string;
}

export interface ChurnFile {
  path: string;
  change_count: number;
  author_count: number;
}

export interface ChurnData {
  top_churned_files: ChurnFile[];
  total_commits: number;
  hotspot_threshold: number;
}

export interface ComparisonEntry {
  model: string;
  ai_debt_score: number;
  issue_count: number;
  top_category: string | null;
  severity_breakdown: Record<string, number>;
  avg_confidence: number | null;
  commit_date: string;
}

export interface AnalysisResult {
  repo_name: string;
  repo_url: string | null;
  commit: { hash: string; short_hash: string; date: string; message: string };
  model: string;
  provider: Provider | "unknown";
  ai_debt_score: number;
  issue_count: number;
  files_analyzed: number;
  summary: string;
  category_breakdown: Record<string, number>;
  severity_breakdown: Record<string, number>;
  issues: Issue[];
  avg_confidence: number | null;
  duplicates_removed: number;
  churn_data: ChurnData | null;
  commits_analyzed: number;
  comparison: Record<string, ComparisonEntry> | null;
}

export interface HistoryPoint {
  commit_hash: string;
  commit_date: string;
  ai_debt_score: number;
  issue_count: number;
}

export async function startAnalysis(
  repoUrl: string,
  mode: "latest" | "history" = "latest",
  provider: Provider = "gemini",
): Promise<{ job_id: string }> {
  const res = await fetch(`${API_URL}/api/analyse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl, mode, provider }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const res = await fetch(`${API_URL}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Job not found (${res.status})`);
  return res.json();
}

export async function getRepos(): Promise<RepoSummary[]> {
  const res = await fetch(`${API_URL}/api/repos`);
  if (!res.ok) throw new Error(`Failed to load repos (${res.status})`);
  return res.json();
}

export async function getResult(repoName: string): Promise<AnalysisResult> {
  const res = await fetch(`${API_URL}/api/results/${repoName}`);
  if (!res.ok) throw new Error(`No results for ${repoName} (${res.status})`);
  return res.json();
}

export async function getHistory(repoName: string): Promise<HistoryPoint[]> {
  const res = await fetch(`${API_URL}/api/results/${repoName}/history`);
  if (!res.ok) return [];
  return res.json();
}

export interface SonarPoint {
  commit_date: string;
  sqale_index: number;
  ncloc: number | null;
  build_status: string;
}

export interface SonarHistory {
  available: boolean;
  data: SonarPoint[] | null;
}

export async function getSonarHistory(repoName: string): Promise<SonarHistory> {
  try {
    const res = await fetch(`${API_URL}/api/sonar/${repoName}/history`);
    if (!res.ok) return { available: false, data: null };
    return res.json();
  } catch {
    return { available: false, data: null };
  }
}
