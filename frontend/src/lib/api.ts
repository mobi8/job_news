import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 10_000,
});

export type JobPosting = {
  title: string;
  company: string;
  location: string;
  url: string;
  match_score: number;
  qualifies: boolean;
  source: string;
  source_label: string;
  country: string;
  fit_tags?: string[];
  first_seen_at?: string;
  dashboard_key?: string;
  description?: string;
};

export type StatsResponse = {
  stats: {
    total_jobs: number;
    new_last_1_day: number;
    new_last_7_days: number;
    new_last_30_days: number;
    top_locations: [string, number][];
    [key: string]: any;
  };
  source_total: { source: string; jobs: number }[];
  source_daily: { source: string; seen_date: string; jobs: number }[];
  updated_at?: string;
  collection_metadata?: Record<string, any>;
  source_metadata?: SourceMetadata[];
};

export type SourceMetadata = {
  id: string;
  label: string;
  kind?: string;
  group?: string;
  enabled?: boolean;
};

export type JobsResponse = {
  total: number;
  limit: number;
  offset: number;
  jobs: JobPosting[];
  counts: {
    recommended: number;
    non_recommended: number;
  };
  status_counts?: {
    unseen: number;
    viewed: number;
    applied: number;
    removed: number;
  };
  collection_metadata?: Record<string, any>;
};

export const fetchStats = async (): Promise<StatsResponse> => {
  const { data } = await client.get("/stats");
  return data;
};

export const fetchSourceMetadata = async (): Promise<{ source_metadata: SourceMetadata[] }> => {
  const { data } = await client.get("/source-metadata");
  return data;
};

export const fetchJobs = async (params: Record<string, any>): Promise<JobsResponse> => {
  const { data } = await client.get("/jobs", { params });
  return data;
};

export const fetchRecommendations = async (): Promise<{ recommendations: JobPosting[] }> => {
  const { data } = await client.get("/recommendations");
  return data;
};

export const fetchNews = async (): Promise<{ news: any[]; updated_at?: string; collection_metadata?: Record<string, any> }> => {
  const { data } = await client.get("/news");
  return data;
};

export const fetchTopics = async (): Promise<{ topics: any[] }> => {
  const { data } = await client.get("/topics");
  return data;
};

export const fetchPlayerMentions = async (): Promise<{ player_mentions: Record<string, any> }> => {
  const { data } = await client.get("/player-mentions");
  return data;
};

export const fetchJobStatuses = async (): Promise<{ statuses: Record<string, string>; rejected_jobs?: Record<string, any> }> => {
  const { data } = await client.get("/job-statuses");
  return data;
};

export const fetchJobDetail = async (jobUrl: string): Promise<{ job: JobPosting }> => {
  const { data } = await client.get(`/job/${encodeURIComponent(jobUrl)}`);
  return data;
};

export const updateJobStatus = async (jobKey: string, status: string, job?: any): Promise<{ success: boolean }> => {
  const { data } = await client.post("/job-status", {
    job_key: jobKey,
    status,
    title: job?.title || "",
    company: job?.company || "",
    location: job?.location || "",
    source: job?.source || "",
    note: "",
  });
  return data;
};
