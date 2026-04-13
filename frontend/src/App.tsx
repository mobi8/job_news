import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  fetchJobs,
  fetchNews,
  fetchStats,
} from "./lib/api";
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

const mainStatusOptions = [
  { label: "안봤음", value: "unseen" },
  { label: "봤음", value: "viewed" },
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

function StatsPanel({ stats }: any) {
  return (
    <section className="glass-panel stats-panel compact">
      <header>
        <h3>통계</h3>
      </header>
      <div className="stats-grid">
        <div>
          <strong>{stats?.total_jobs ?? "—"}</strong>
          <span>전체</span>
        </div>
        <div>
          <strong>{stats?.new_last_1_day ?? "—"}</strong>
          <span>24h</span>
        </div>
        <div>
          <strong>{stats?.new_last_7_days ?? "—"}</strong>
          <span>7일</span>
        </div>
        <div>
          <strong>{stats?.new_last_30_days ?? "—"}</strong>
          <span>30일</span>
        </div>
      </div>
    </section>
  );
}

// Category Tabs with hierarchical structure
function CategoryTabs({
  mainStatus,
  subStatus,
  onMainStatusChange,
  onSubStatusChange,
}: {
  mainStatus: string;
  subStatus: string;
  onMainStatusChange: (value: string) => void;
  onSubStatusChange: (value: string) => void;
}) {
  return (
    <section className="glass-panel category-tabs-section">
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
            {option.label}
          </button>
        ))}
      </div>
      {mainStatus === "unseen" && (
        <div className="category-sub-tabs">
          <button
            className={`category-sub-tab ${subStatus === "" ? "active" : ""}`}
            onClick={() => onSubStatusChange("")}
          >
            전체
          </button>
          {subStatusOptions.map((option) => (
            <button
              key={option.value}
              className={`category-sub-tab ${subStatus === option.value ? "active" : ""}`}
              onClick={() => onSubStatusChange(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Record<string, any>;
  onChange: (values: Record<string, any>) => void;
}) {
  return (
    <section className="glass-panel filter-panel">
      <div className="filter-row">
        <input
          type="search"
          placeholder="제목, 회사, 위치 검색"
          value={filters.q}
          onChange={(event) => onChange({ ...filters, q: event.target.value })}
        />
        <select
          value={filters.source}
          onChange={(event) =>
            onChange({ ...filters, source: event.target.value })
          }
        >
          {filterOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <select
          value={filters.country}
          onChange={(event) =>
            onChange({ ...filters, country: event.target.value })
          }
        >
          {countryOptions.map((option) => (
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
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <label style={{ whiteSpace: "nowrap" }}>
            최소 점수: {filters.min_score}
          </label>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={filters.min_score}
            onChange={(event) =>
              onChange({ ...filters, min_score: parseInt(event.target.value) })
            }
            style={{ flex: 1 }}
          />
        </div>
      </div>
    </section>
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
function MetadataBar({ jobsQuery, statsQuery }: any) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const collectedAt = jobsQuery.data?.collection_metadata?.collected_at;
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
}: {
  jobsData?: any;
  isLoading: boolean;
  filters?: any;
  mainStatus: string;
  subStatus: string;
}) {
  const [jobStatuses, setJobStatuses] = useState<Record<string, string>>(() => {
    const saved = localStorage.getItem("jobStatuses");
    return saved ? JSON.parse(saved) : {};
  });

  const updateJobStatus = (jobKey: string, status: string) => {
    const updated = { ...jobStatuses, [jobKey]: status };
    setJobStatuses(updated);
    localStorage.setItem("jobStatuses", JSON.stringify(updated));
  };

  const sortedAndFiltered = useMemo(() => {
    let jobs = jobsData?.jobs || [];

    // Filter by main status
    if (mainStatus) {
      jobs = jobs.filter((job: any) => (job.status || "unseen") === mainStatus);
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
      jobs = jobs.filter((job: any) => (job.status || "unseen") === filters.status);
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
  }, [jobsData?.jobs, filters?.status, filters?.sortBy, mainStatus, subStatus]);

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
        return (
        <div
          key={jobKey}
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
              <div className="gauge-bar" style={{ width: `${job.match_score}%` }} />
              <span className="gauge-label">{job.match_score}</span>
            </div>
          </div>
          <div className="card-actions">
            <a href={job.url} target="_blank" rel="noreferrer" className="card-link">
              링크 열기 ↗
            </a>
          </div>

          <div className="card-status-buttons">
            <button
              className={`status-btn ${currentStatus === "unseen" ? "active" : ""}`}
              onClick={() => updateJobStatus(jobKey, "unseen")}
            >
              안봤음
            </button>
            <button
              className={`status-btn ${currentStatus === "viewed" ? "active" : ""}`}
              onClick={() => updateJobStatus(jobKey, "viewed")}
            >
              👁️
            </button>
            <button
              className={`status-btn ${currentStatus === "applied" ? "active" : ""}`}
              onClick={() => updateJobStatus(jobKey, "applied")}
            >
              ✓
            </button>
            <button
              className={`status-btn ${currentStatus === "removed" ? "active" : ""}`}
              onClick={() => updateJobStatus(jobKey, "removed")}
            >
              ✕
            </button>
          </div>
          <span className="time-badge">
            {formatTime(job.first_seen_at)}
          </span>
        </div>
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
  onTabChange,
  mainStatus,
  subStatus,
}: {
  jobsData?: any;
  jobsLoading: boolean;
  newsData?: any[];
  filters?: any;
  activeTab: "jobs" | "news";
  onTabChange: (tab: "jobs" | "news") => void;
  mainStatus: string;
  subStatus: string;
}) {
  const jobCount = jobsData?.total ?? 0;
  const newsCount = newsData?.length ?? 0;

  return (
    <>
      <div className="main-tabs-container">
        <button
          className={`main-tab ${activeTab === "jobs" ? "active" : ""}`}
          onClick={() => onTabChange("jobs")}
        >
          📋 공고 ({jobCount})
          {jobsData?.counts && (
            <span className="main-tab-meta">
              {jobsData.counts.recommended} 추천
            </span>
          )}
        </button>
        <button
          className={`main-tab ${activeTab === "news" ? "active" : ""}`}
          onClick={() => onTabChange("news")}
        >
          📰 뉴스 ({newsCount})
        </button>
      </div>
      <section className="glass-panel section-container">

      <div className="section-content">
        {activeTab === "jobs" && (
          <JobsList jobsData={jobsData} isLoading={jobsLoading} filters={filters} mainStatus={mainStatus} subStatus={subStatus} />
        )}
        {activeTab === "news" && <NewsList newsData={newsData} />}
      </div>
      </section>
    </>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState<"jobs" | "news">("jobs");
  const [mainStatus, setMainStatus] = useState("unseen");
  const [subStatus, setSubStatus] = useState("");
  const [filters, setFilters] = useState({
    source: "",
    country: "",
    q: "",
    qualifies: false,
    min_score: 60,
    status: "",
    sortBy: "date-desc",
  });

  const statsQuery = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    refetchInterval: 30000, // Auto-refetch every 30s
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", filters],
    queryFn: () =>
      fetchJobs({
        source: filters.source || undefined,
        country: filters.country || undefined,
        q: filters.q || undefined,
        qualifies: filters.qualifies ? true : undefined,
        min_score: filters.min_score || 0,
        limit: 50,
      }),
    keepPreviousData: true,
    refetchInterval: 30000, // Auto-refetch every 30s
  });

  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: async () => {
      const { data } = await axios.get("/api/news");
      return data.news || [];
    },
  });

  const countryCounts = useMemo(() => {
    if (!jobsQuery.data) return [];
    const counts: Record<string, number> = {};
    jobsQuery.data.jobs.forEach((job: any) => {
      counts[job.country || "Unknown"] = (counts[job.country || "Unknown"] || 0) + 1;
    });
    return Object.entries(counts);
  }, [jobsQuery.data]);

  return (
    <div className="app-shell">
      <MetadataBar jobsQuery={jobsQuery} statsQuery={statsQuery} />

      <header className="glass-panel hero">
        <div>
          <h1>Job Watch</h1>
          <p>실시간 채용공고 & 뉴스 모니터링 대시보드</p>
        </div>
        <div className="hero-badges">
          {countryCounts.map(([country, value]) => (
            <span key={country} className="status-pill">
              {country}: {value}
            </span>
          ))}
        </div>
      </header>

      {activeTab === "jobs" && (
        <StatsPanel stats={statsQuery.data?.stats ?? statsQuery.data} />
      )}

      {activeTab === "jobs" && (
        <>
          <CategoryTabs
            mainStatus={mainStatus}
            subStatus={subStatus}
            onMainStatusChange={setMainStatus}
            onSubStatusChange={setSubStatus}
          />
          <FilterBar filters={filters} onChange={setFilters} />
        </>
      )}

      <ContentSection
        jobsData={jobsQuery.data}
        jobsLoading={jobsQuery.isLoading}
        newsData={newsQuery.data}
        filters={filters}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        mainStatus={mainStatus}
        subStatus={subStatus}
      />
    </div>
  );
}

export default App;
