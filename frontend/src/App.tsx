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

// Jobs Section with List + Detail
function JobsSection({
  jobsData,
  isLoading,
}: {
  jobsData?: any;
  isLoading: boolean;
}) {
  const [selectedJob, setSelectedJob] = useState<any>(null);

  const displayJob = selectedJob || jobsData?.jobs?.[0];

  return (
    <section className="glass-panel section-container">
      <h2 className="section-title">공고 관리</h2>
      <div className="section-layout">
        <div className="list-pane">
          <div className="list-header">
            <span>공고 ({jobsData?.total ?? 0})</span>
            <span className="list-meta">
              {jobsData?.counts?.recommended ?? 0} 추천 ·{" "}
              {jobsData?.counts?.non_recommended ?? 0} 보류
            </span>
          </div>
          <div className="list-scroll">
            {isLoading ? (
              <div className="loading">로딩 중...</div>
            ) : jobsData?.jobs?.length ? (
              jobsData.jobs.map((job: any) => (
                <div
                  key={job.dashboard_key ?? job.url}
                  className={`list-item ${
                    selectedJob?.url === job.url ? "active" : ""
                  }`}
                  onClick={() => setSelectedJob(job)}
                >
                  <div className="list-item-title">{job.title}</div>
                  <div className="list-item-subtitle">{job.company}</div>
                  <div className="list-item-meta">
                    <span className="score">{job.match_score}</span>
                    <span
                      className={`status ${
                        job.qualifies ? "recommended" : "caution"
                      }`}
                    >
                      {job.qualifies ? "추천" : "보류"}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty">공고 없음</div>
            )}
          </div>
        </div>

        <div className="detail-pane">
          {displayJob ? (
            <div className="detail-content">
              <h3>{displayJob.title}</h3>
              <div className="detail-field">
                <label>회사</label>
                <p>{displayJob.company}</p>
              </div>
              <div className="detail-field">
                <label>위치</label>
                <p>{displayJob.location}</p>
              </div>
              <div className="detail-field">
                <label>국가</label>
                <p>{displayJob.country}</p>
              </div>
              <div className="detail-field">
                <label>스코어</label>
                <p className="score-large">{displayJob.match_score}</p>
              </div>
              <div className="detail-field">
                <label>상태</label>
                <p
                  className={`status-large ${
                    displayJob.qualifies ? "recommended" : "caution"
                  }`}
                >
                  {displayJob.qualifies ? "추천" : "보류"}
                </p>
              </div>
              <div className="detail-field">
                <label>소스</label>
                <p>{displayJob.source_label}</p>
              </div>
              {displayJob.fit_tags?.length > 0 && (
                <div className="detail-field">
                  <label>태그</label>
                  <div className="tags">
                    {displayJob.fit_tags.map((tag: string) => (
                      <span key={tag} className="tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <a
                href={displayJob.url}
                target="_blank"
                rel="noreferrer"
                className="detail-link"
              >
                원문 보기 →
              </a>
            </div>
          ) : (
            <div className="detail-empty">항목을 선택해주세요</div>
          )}
        </div>
      </div>
    </section>
  );
}

// News Section with List + Detail
function NewsSection({
  newsData,
}: {
  newsData?: any[];
}) {
  const [selectedNews, setSelectedNews] = useState<any>(null);

  const displayNews = selectedNews || newsData?.[0];

  return (
    <section className="glass-panel section-container">
      <h2 className="section-title">뉴스</h2>
      <div className="section-layout">
        <div className="list-pane">
          <div className="list-header">
            <span>뉴스 ({newsData?.length ?? 0})</span>
          </div>
          <div className="list-scroll">
            {newsData?.length ? (
              newsData.map((item: any) => (
                <div
                  key={item.url}
                  className={`list-item ${
                    selectedNews?.url === item.url ? "active" : ""
                  }`}
                  onClick={() => setSelectedNews(item)}
                >
                  <div className="list-item-title">{item.title}</div>
                  <div className="list-item-subtitle">
                    {item.source_label || item.source}
                  </div>
                  <div className="list-item-meta">
                    <span className="source-tag">
                      {item.source_emoji || "📰"}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty">뉴스 없음</div>
            )}
          </div>
        </div>

        <div className="detail-pane">
          {displayNews ? (
            <div className="detail-content">
              <h3>{displayNews.title}</h3>
              <div className="detail-field">
                <label>소스</label>
                <p>
                  {displayNews.source_emoji && (
                    <span>{displayNews.source_emoji} </span>
                  )}
                  {displayNews.source_label || displayNews.source}
                </p>
              </div>
              {displayNews.source_description && (
                <div className="detail-field">
                  <label>설명</label>
                  <p>{displayNews.source_description}</p>
                </div>
              )}
              <a
                href={displayNews.url}
                target="_blank"
                rel="noreferrer"
                className="detail-link"
              >
                기사 보기 →
              </a>
            </div>
          ) : (
            <div className="detail-empty">항목을 선택해주세요</div>
          )}
        </div>
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

      <JobsSection
        jobsData={jobsQuery.data}
        isLoading={jobsQuery.isLoading}
      />

      <NewsSection newsData={newsQuery.data} />
    </div>
  );
}

export default App;
