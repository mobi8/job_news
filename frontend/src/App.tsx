import { useMemo, useState } from "react";
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
  { label: "LinkedIn UAE", value: "linkedin_public" },
  { label: "Indeed UAE", value: "indeed_uae" },
  { label: "LinkedIn Malta", value: "linkedin_malta" },
];

const countryOptions = [
  { label: "전체 국가", value: "" },
  { label: "UAE", value: "UAE" },
  { label: "Georgia", value: "Georgia" },
  { label: "Malta", value: "Malta" },
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
    <section className="glass-panel stats-panel">
      <header>
        <h2>통계</h2>
        <p>마지막 업데이트: {stats?.updated_at ?? "로딩 중..."}</p>
      </header>
      <div className="stats-grid">
        <div>
          <strong>{stats?.total_jobs ?? "—"}</strong>
          <span>전체 추적</span>
        </div>
        <div>
          <strong>{stats?.new_last_1_day ?? "—"}</strong>
          <span>최근 24h</span>
        </div>
        <div>
          <strong>{stats?.new_last_7_days ?? "—"}</strong>
          <span>최근 7일</span>
        </div>
        <div>
          <strong>{stats?.new_last_30_days ?? "—"}</strong>
          <span>최근 30일</span>
        </div>
      </div>
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
        <label>
          <input
            type="checkbox"
            checked={filters.qualifies}
            onChange={(event) =>
              onChange({ ...filters, qualifies: event.target.checked })
            }
          />
          추천만
        </label>
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

// Jobs List
function JobsList({
  jobsData,
  isLoading,
}: {
  jobsData?: any;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <div className="loading">로딩 중...</div>;
  }

  if (!jobsData?.jobs?.length) {
    return <div className="empty">공고 없음</div>;
  }

  return (
    <div className="list-grid">
      {jobsData.jobs.map((job: any) => (
        <a
          key={job.dashboard_key ?? job.url}
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
            <span className="score-badge">{job.match_score}</span>
            <span className="time-badge">
              {formatTime(job.first_seen_at)}
            </span>
          </div>
        </a>
      ))}
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
}: {
  jobsData?: any;
  jobsLoading: boolean;
  newsData?: any[];
}) {
  const [activeTab, setActiveTab] = useState<"jobs" | "news">("jobs");

  const jobCount = jobsData?.total ?? 0;
  const newsCount = newsData?.length ?? 0;

  return (
    <section className="glass-panel section-container">
      <div className="section-tabs">
        <button
          className={`tab ${activeTab === "jobs" ? "active" : ""}`}
          onClick={() => setActiveTab("jobs")}
        >
          공고 ({jobCount})
          {jobsData?.counts && (
            <span className="tab-meta">
              {jobsData.counts.recommended} 추천
            </span>
          )}
        </button>
        <button
          className={`tab ${activeTab === "news" ? "active" : ""}`}
          onClick={() => setActiveTab("news")}
        >
          뉴스 ({newsCount})
        </button>
      </div>

      <div className="section-content">
        {activeTab === "jobs" && (
          <JobsList jobsData={jobsData} isLoading={jobsLoading} />
        )}
        {activeTab === "news" && <NewsList newsData={newsData} />}
      </div>
    </section>
  );
}

function App() {
  const [filters, setFilters] = useState({
    source: "",
    country: "",
    q: "",
    qualifies: false,
  });

  const statsQuery = useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
  });

  const jobsQuery = useQuery({
    queryKey: ["jobs", filters],
    queryFn: () =>
      fetchJobs({
        source: filters.source || undefined,
        country: filters.country || undefined,
        q: filters.q || undefined,
        qualifies: filters.qualifies ? true : undefined,
        limit: 50,
      }),
    keepPreviousData: true,
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
      <HealthStatus />

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

      <StatsPanel stats={statsQuery.data?.stats ?? statsQuery.data} />
      <FilterBar filters={filters} onChange={setFilters} />

      <ContentSection
        jobsData={jobsQuery.data}
        jobsLoading={jobsQuery.isLoading}
        newsData={newsQuery.data}
      />
    </div>
  );
}

export default App;
