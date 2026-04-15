import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  fetchJobs,
  fetchNews,
  fetchStats,
  fetchJobStatuses,
  updateJobStatus as apiUpdateJobStatus,
} from "./lib/api.ts";
import type { JobsResponse, StatsResponse } from "./lib/api.ts";
import "./App.css";

const filterOptions = [
  { label: "전체", value: "" },
  { label: "LinkedIn Public", value: "linkedin_public" },
  { label: "Indeed UAE", value: "indeed_uae" },
  { label: "Jobvite (Pragmatic Play)", value: "jobvite_pragmaticplay" },
  { label: "Jobrapido UAE", value: "jobrapido_uae" },
  { label: "LinkedIn Malta", value: "linkedin_malta" },
  { label: "JobLeads", value: "jobleads" },
  { label: "LinkedIn Georgia", value: "linkedin_georgia" },
  { label: "iGaming Recruitment", value: "igamingrecruitment" },
  { label: "SmartRecruitment", value: "smartrecruitment" },
];

const countryOptions = [
  { label: "전체 국가", value: "" },
  { label: "UAE", value: "UAE" },
  { label: "Georgia", value: "Georgia" },
  { label: "Malta", value: "Malta" },
];


const statusOptions = [
  { label: "전체 상태", value: "" },
  { label: "안봤음", value: "unseen" },
  { label: "봤음", value: "viewed" },
  { label: "지원함", value: "applied" },
  { label: "제거됨", value: "removed" },
];

const sortOptions = [
  { label: "최신순 (↓)", value: "date-desc" },
  { label: "오래된순 (↑)", value: "date-asc" },
  { label: "점수높음 (↓)", value: "score-desc" },
  { label: "점수낮음 (↑)", value: "score-asc" },
];

type FilterState = {
  source: string;
  country: string;
  q: string;
  qualifies: boolean;
  min_score: number;
  status: string;
  sortBy: string;
};

type StatusKey = "unseen" | "viewed" | "applied" | "removed";

const mainStatusOptions: { label: string; value: StatusKey }[] = [
  { label: "안봤음", value: "unseen" },
  { label: "저장", value: "viewed" },
  { label: "지원함", value: "applied" },
  { label: "제거", value: "removed" },
];

const subStatusOptions = [
  { label: "추천", value: "recommended" },
  { label: "참고", value: "reference" },
];

// API Health Status Component
function HealthStatus() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await axios.get("/api/healthz");
      return data;
    },
    refetchInterval: 30000,
  });

  const isHealthy = healthQuery.data?.status === "ok";

  return (
    <div className="health-status">
      <div className={`health-indicator ${isHealthy ? "healthy" : "unhealthy"}`}>
        <span className="health-dot" />
        {isHealthy ? "API Online" : "API Offline"}
      </div>
    </div>
  );
}

function StatsSummary({ stats }: { stats?: StatsResponse["stats"] }) {
  const items = [
    { label: "전체", value: stats?.total_jobs ?? "—" },
    { label: "지난 24h", value: stats?.new_last_1_day ?? "—" },
    { label: "지난 7일", value: stats?.new_last_7_days ?? "—" },
    { label: "지난 30일", value: stats?.new_last_30_days ?? "—" },
  ];

  return (
    <div className="stats-summary">
      {items.map((item) => (
        <div key={item.label} className="stats-item">
          <span className="stats-label">{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );
}

// Category Tabs with hierarchical structure
function CategoryTabs({
  mainStatus,
  subStatus,
  statusCounts,
  subStatusCounts,
  onMainStatusChange,
  onSubStatusChange,
}: {
  mainStatus: string;
  subStatus: string;
  statusCounts: Record<StatusKey, number>;
  subStatusCounts: { total: number; recommended: number; reference: number };
  onMainStatusChange: (value: string) => void;
  onSubStatusChange: (value: string) => void;
}) {
  return (
    <div className="category-tabs-section">
      <div className="category-main-tabs">
        {mainStatusOptions.map((option) => (
          <button
            key={option.value}
            className={`category-tab ${mainStatus === option.value ? "active" : ""}`}
            onClick={() => {
              onMainStatusChange(option.value);
              onSubStatusChange(""); // Reset sub-status
            }}
          >
            <span>{option.label}</span>
            <span className="category-count">
              {statusCounts[option.value] ?? 0}
            </span>
          </button>
        ))}
      </div>
      {mainStatus === "unseen" && (
        <div className="category-sub-tabs">
          <button
            className={`category-sub-tab ${subStatus === "" ? "active" : ""}`}
            onClick={() => onSubStatusChange("")}
          >
            <span>전체</span>
            <span className="category-count">{subStatusCounts.total}</span>
          </button>
          <button
            className={`category-sub-tab ${subStatus === "recommended" ? "active" : ""}`}
            onClick={() => onSubStatusChange("recommended")}
          >
            <span>추천</span>
            <span className="category-count">{subStatusCounts.recommended}</span>
          </button>
          <button
            className={`category-sub-tab ${subStatus === "reference" ? "active" : ""}`}
            onClick={() => onSubStatusChange("reference")}
          >
            <span>참고</span>
            <span className="category-count">{subStatusCounts.reference}</span>
          </button>
        </div>
      )}
    </div>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: FilterState;
  onChange: (values: FilterState) => void;
}) {
  return (
    <div className="filter-frame">
      <div className="filter-inputs">
        <input
          type="search"
          placeholder="제목, 회사, 위치 검색"
          value={filters.q}
          onChange={(event) => onChange({ ...filters, q: event.target.value })}
        />
        <select
          value={filters.source}
          onChange={(event) => onChange({ ...filters, source: event.target.value })}
        >
          {filterOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={filters.sortBy}
          onChange={(event) =>
            onChange({ ...filters, sortBy: event.target.value })
          }
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// Format timestamp for display
function formatTime(timestamp?: string) {
  if (!timestamp) return "—";
  const date = new Date(timestamp);
  return date.toLocaleString("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Metadata Bar Component
function MetadataBar({ jobsQuery, newsQuery, activeTab }: any) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  // Always use jobsQuery as the source of truth for collection_metadata
  const collectedAt = jobsQuery?.data?.collection_metadata?.collected_at || jobsQuery?.data?.updated_at;
  const batchNewCount = jobsQuery?.data?.collection_metadata?.new_jobs_this_run;
  const formattedScrapTime = collectedAt
    ? new Date(collectedAt).toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : "—";

  const nextBatchTime = (() => {
    // 다음 배치는 매시간 정각 기준 (예: 매시간 정각에 실행)
    const nextHour = new Date(now);
    nextHour.setHours(nextHour.getHours() + 1, 0, 0, 0);
    return nextHour.toLocaleString("ko-KR", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  })();

  return (
    <section className="glass-panel metadata-bar">
      <div className="metadata-content">
        <div className="metadata-item">
          <span className="metadata-label">최신 스크랩:</span>
          <span className="metadata-value">{formattedScrapTime}</span>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">이번 배치 신규:</span>
          <span className="metadata-value">{batchNewCount ?? "—"}</span>
        </div>
        <div className="metadata-item">
          <span className="metadata-label">다음 배치:</span>
          <span className="metadata-value">{nextBatchTime}</span>
        </div>
      </div>
    </section>
  );
}

// Jobs List
function JobsList({
  jobsData,
  isLoading,
  filters,
  mainStatus,
  subStatus,
  jobStatuses,
  onUpdateJobStatus,
}: {
  jobsData?: any;
  isLoading: boolean;
  filters?: any;
  mainStatus: string;
  subStatus: string;
  jobStatuses: Record<string, StatusKey>;
  onUpdateJobStatus: (jobKey: string, status: StatusKey) => void;
}) {

  const sortedAndFiltered = useMemo(() => {
    let jobs = jobsData?.jobs || [];
    const getJobKey = (job: any) => job.dashboard_key ?? job.url;
    const getJobStatus = (job: any): StatusKey =>
      jobStatuses[getJobKey(job)] || "unseen";

    // For removed/applied statuses, include past jobs from jobStatuses
    if (mainStatus === "removed" || mainStatus === "applied") {
      const jobKeys = new Set(jobs.map(getJobKey));
      Object.entries(jobStatuses).forEach(([jobKey, status]) => {
        if (status === mainStatus && !jobKeys.has(jobKey)) {
          // Extract title from jobKey (format: "source|id|title|company")
          const parts = jobKey.split("|");
          const title = parts[2] || jobKey;
          jobs.push({ dashboard_key: jobKey, url: jobKey, title, company: parts[3] || "", location: "", source: parts[0] || "" });
        }
      });
    }

    // Filter by main status
    if (mainStatus) {
      jobs = jobs.filter((job: any) => getJobStatus(job) === mainStatus);
    }

    // Filter by sub-status (only for unseen)
    if (mainStatus === "unseen" && subStatus) {
      jobs = jobs.filter((job: any) => {
        if (subStatus === "recommended") return job.qualifies === true;
        if (subStatus === "reference") return job.qualifies === false;
        return true;
      });
    }

    // Filter by other criteria
    if (filters?.status) {
        jobs = jobs.filter((job: any) => getJobStatus(job) === filters.status);
    }

    // Sort
    const sorted = [...jobs];
    switch (filters?.sortBy) {
      case "date-asc":
        sorted.sort((a: any, b: any) =>
          new Date(a.first_seen_at || 0).getTime() - new Date(b.first_seen_at || 0).getTime()
        );
        break;
      case "score-desc":
        sorted.sort((a: any, b: any) => (b.match_score || 0) - (a.match_score || 0));
        break;
      case "score-asc":
        sorted.sort((a: any, b: any) => (a.match_score || 0) - (b.match_score || 0));
        break;
      case "date-desc":
      default:
        sorted.sort((a: any, b: any) =>
          new Date(b.first_seen_at || 0).getTime() - new Date(a.first_seen_at || 0).getTime()
        );
    }
    return sorted;
  }, [jobsData?.jobs, filters?.status, filters?.sortBy, mainStatus, subStatus, jobStatuses]);

  if (isLoading) {
    return <div className="loading">로딩 중...</div>;
  }

  if (!sortedAndFiltered?.length) {
    return <div className="empty">공고 없음</div>;
  }

  return (
    <div className="list-grid">
      {sortedAndFiltered.map((job: any) => {
        const jobKey = job.dashboard_key ?? job.url;
        const currentStatus = jobStatuses[jobKey] || "unseen";
        const hue = (job.match_score / 100) * 120;
        const gaugeGradient = `linear-gradient(90deg, hsl(${hue}, 80%, 40%), hsl(${hue}, 100%, 55%))`;
        return (
        <a
          key={jobKey}
          href={job.url}
          target="_blank"
          rel="noreferrer"
          className="list-card"
        >
          <div className="card-header">
            <div className="card-title">{job.title}</div>
            <span
              className={`status-badge ${
                job.qualifies ? "recommended" : "caution"
              }`}
            >
              {job.qualifies ? "추천" : "보류"}
            </span>
          </div>
          <div className="card-subtitle">{job.company}</div>
          <div className="card-location">{job.location}</div>
          <div className="card-footer">
            <div className="score-gauge">
              <div className="gauge-bar" style={{ width: `${job.match_score}%`, background: gaugeGradient }} />
              <span className="gauge-label" style={{ color: `hsl(${hue}, 100%, 55%)` }}>{job.match_score}</span>
            </div>
          </div>

          <div className="card-status-buttons">
            <button
              className={`status-btn ${currentStatus === "unseen" ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                onUpdateJobStatus(jobKey, "unseen");
              }}
            >
              안봤음
            </button>
            <button
              className={`status-btn ${currentStatus === "viewed" ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                onUpdateJobStatus(jobKey, "viewed");
              }}
            >
              저장
            </button>
            <button
              className={`status-btn ${currentStatus === "applied" ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                onUpdateJobStatus(jobKey, "applied");
              }}
            >
              지원함
            </button>
            <button
              className={`status-btn ${currentStatus === "removed" ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                onUpdateJobStatus(jobKey, "removed");
              }}
            >
              제거
            </button>
          </div>
          <span className="time-badge">
            <span className="source-label">{job.source}</span>
            {formatTime(job.first_seen_at)}
          </span>
        </a>
      );
      })}
    </div>
  );
}

// News List
function NewsList({
  newsData,
}: {
  newsData?: any[];
}) {
  if (!newsData?.length) {
    return <div className="empty">뉴스 없음</div>;
  }

  return (
    <div className="list-grid">
      {newsData.map((item: any) => (
        <a
          key={item.url}
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="list-card news-card"
        >
          <div className="card-header">
            <div className="card-title">{item.title}</div>
            {item.source_emoji && (
              <span className="emoji-badge">{item.source_emoji}</span>
            )}
          </div>
          <div className="card-subtitle">
            {item.source_label || item.source}
          </div>
          {item.source_description && (
            <div className="card-description">{item.source_description}</div>
          )}
          <span className="time-badge">
            {formatTime(item.published_at || item.discovered_at || item.created_at)}
          </span>
        </a>
      ))}
    </div>
  );
}

// Content Section with Tabs
function ContentSection({
  jobsData,
  jobsLoading,
  newsData,
  filters,
  activeTab,
  mainStatus,
  subStatus,
  jobStatuses,
  onUpdateJobStatus,
}: {
  jobsData?: any;
  jobsLoading: boolean;
  newsData?: any[];
  filters?: any;
  activeTab: "jobs" | "news";
  mainStatus: string;
  subStatus: string;
  jobStatuses: Record<string, StatusKey>;
  onUpdateJobStatus: (jobKey: string, status: StatusKey) => void;
}) {
  return (
    <div className="section-content">
      {activeTab === "jobs" && (
        <JobsList
          jobsData={jobsData}
          isLoading={jobsLoading}
          filters={filters}
          mainStatus={mainStatus}
          subStatus={subStatus}
          jobStatuses={jobStatuses}
          onUpdateJobStatus={onUpdateJobStatus}
        />
      )}
      {activeTab === "news" && <NewsList newsData={newsData} />}
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<"jobs" | "news">("jobs");
  const [mainStatus, setMainStatus] = useState("unseen");
  const [subStatus, setSubStatus] = useState("");
  const [jobStatuses, setJobStatuses] = useState<Record<string, StatusKey>>({});
  const [filters, setFilters] = useState<FilterState>({
    source: "",
    country: "",
    q: "",
    qualifies: false,
    min_score: 60,
    status: "",
    sortBy: "date-desc",
  });

  // Load job statuses from API on mount
  useEffect(() => {
    fetchJobStatuses()
      .then((data) => {
        const converted: Record<string, StatusKey> = {};
        Object.entries(data.statuses).forEach(([key, value]) => {
          if (["unseen", "viewed", "applied", "removed"].includes(value)) {
            converted[key] = value as StatusKey;
          }
        });
        setJobStatuses(converted);
      })
      .catch((err) => console.error("Failed to load job statuses:", err));
  }, []);

  const statsQuery = useQuery<StatsResponse, Error, StatsResponse, ["stats"]>({
    queryKey: ["stats"],
    queryFn: fetchStats,
    refetchInterval: 30000,
  });

  const jobsQuery = useQuery<
    JobsResponse,
    Error,
    JobsResponse,
    readonly ["jobs", string, string, string, boolean, number, number]
  >({
    queryKey: [
      "jobs",
      filters.source,
      filters.country,
      filters.q,
      filters.qualifies,
      filters.min_score,
      10000,
    ],
    queryFn: () =>
      fetchJobs({
        source: filters.source || undefined,
        country: filters.country || undefined,
        q: filters.q || undefined,
        qualifies: filters.qualifies ? true : undefined,
        min_score: filters.min_score || 0,
        limit: 10000,
      }),
    refetchInterval: 30000,
  });

  const newsQuery = useQuery<any[], Error, any[], ["news"]>({
    queryKey: ["news"],
    queryFn: async () => {
      const { data } = await axios.get("/api/news");
      return data.news || [];
    },
  });

  const updateJobStatus = (jobKey: string, status: StatusKey) => {
    // Update local state immediately for UI responsiveness
    setJobStatuses((prev) => {
      const next = { ...prev };
      if (status === "unseen") {
        delete next[jobKey];
      } else {
        next[jobKey] = status;
      }
      return next;
    });

    // Sync with API
    const allJobs = jobsQuery.data?.jobs || [];
    const job = allJobs.find((j: any) => (j.dashboard_key ?? j.url) === jobKey);
    apiUpdateJobStatus(jobKey, status, job)
      .then(() => {
        // Reload all statuses from API after update
        return fetchJobStatuses().then((data) => {
          const converted: Record<string, StatusKey> = {};
          Object.entries(data.statuses).forEach(([key, value]) => {
            if (["unseen", "viewed", "applied", "removed"].includes(value)) {
              converted[key] = value as StatusKey;
            }
          });
          setJobStatuses(converted);
        });
      })
      .catch((err) => {
        console.error("Failed to update job status:", err);
      });
  };


  const jobCount = jobsQuery.data?.total ?? 0;
  const newsCount = newsQuery.data?.length ?? 0;
  const statusCounts = useMemo<Record<StatusKey, number>>(() => {
    const initial: Record<StatusKey, number> = {
      unseen: 0,
      viewed: 0,
      applied: 0,
      removed: 0,
    };
    const jobs = jobsQuery.data?.jobs ?? [];
    const jobKeys = new Set(jobs.map((j: any) => j.dashboard_key ?? j.url));

    // Count jobs from current results
    jobs.forEach((job: any) => {
      const jobKey = job.dashboard_key ?? job.url;
      const currentStatus: StatusKey = jobStatuses[jobKey] || "unseen";
      initial[currentStatus] = (initial[currentStatus] || 0) + 1;
    });

    // Count all past statuses (viewed, applied, removed from jobStatuses)
    Object.entries(jobStatuses).forEach(([jobKey, status]) => {
      if (!jobKeys.has(jobKey)) {
        initial[status as StatusKey] = (initial[status as StatusKey] || 0) + 1;
      }
    });

    return initial;
  }, [jobStatuses, jobsQuery.data?.jobs]);

  const subStatusCounts = useMemo(() => {
    // Calculate sub-status counts only for unseen jobs
    const unseenJobs = (jobsQuery.data?.jobs || []).filter(
      (job: any) => (jobStatuses[job.dashboard_key ?? job.url] || "unseen") === "unseen"
    );
    return {
      total: unseenJobs.length,
      recommended: unseenJobs.filter((job: any) => job.qualifies === true).length,
      reference: unseenJobs.filter((job: any) => job.qualifies === false).length,
    };
  }, [jobsQuery.data?.jobs, jobStatuses]);

  return (
    <div className="app-shell">
      <div className="main-tabs-row top-tabs">
        <button
          className={`main-tab ${activeTab === "jobs" ? "active" : ""}`}
          onClick={() => setActiveTab("jobs")}
        >
          공고 ({jobCount})
        </button>
        <button
          className={`main-tab ${activeTab === "news" ? "active" : ""}`}
          onClick={() => setActiveTab("news")}
        >
          뉴스 ({newsCount})
        </button>
      </div>

      {activeTab === "jobs" && (
        <section className="glass-panel controls-panel compact-panel">
          <div className="controls-card category-card">
            <CategoryTabs
              mainStatus={mainStatus}
              subStatus={subStatus}
              statusCounts={statusCounts}
              subStatusCounts={subStatusCounts}
              onMainStatusChange={setMainStatus}
              onSubStatusChange={setSubStatus}
            />
            <div className="slider-panel">
              <div className="slider-label">최소 점수: {filters.min_score}</div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={filters.min_score}
                onChange={(event) =>
                  setFilters({ ...filters, min_score: parseInt(event.target.value) })
                }
              />
            </div>
          </div>
          <div className="controls-card filter-card">
            <FilterBar filters={filters} onChange={(values) => setFilters(values)} />
          </div>
        </section>
      )}

      <MetadataBar jobsQuery={jobsQuery} newsQuery={newsQuery} activeTab={activeTab} />

      {activeTab === "jobs" && (
        <div className="country-bookmarks">
          <button
            className={`bookmark ${filters.country === "" ? "active" : ""}`}
            onClick={() => setFilters({ ...filters, country: "" })}
          >
            전체
          </button>
          <button
            className={`bookmark UAE ${filters.country === "UAE" ? "active" : ""}`}
            onClick={() => setFilters({ ...filters, country: "UAE" })}
          >
            UAE
          </button>
          <button
            className={`bookmark Georgia ${filters.country === "Georgia" ? "active" : ""}`}
            onClick={() => setFilters({ ...filters, country: "Georgia" })}
          >
            Georgia
          </button>
          <button
            className={`bookmark Malta ${filters.country === "Malta" ? "active" : ""}`}
            onClick={() => setFilters({ ...filters, country: "Malta" })}
          >
            Malta
          </button>
        </div>
      )}

      <section className="glass-panel section-panel">
        <ContentSection
          jobsData={jobsQuery.data}
          jobsLoading={jobsQuery.isLoading}
          newsData={newsQuery.data}
          filters={filters}
          activeTab={activeTab}
          mainStatus={mainStatus}
          subStatus={subStatus}
          jobStatuses={jobStatuses}
          onUpdateJobStatus={updateJobStatus}
        />
      </section>
    </div>
  );
}

export default App;
