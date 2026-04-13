import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchJobs,
  fetchNews,
  fetchPlayerMentions,
  fetchRecommendations,
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

function StatsPanel({ stats }: any) {
  return (
    <section className="glass-panel stats-panel">
      <header>
        <h2>이상치 통계</h2>
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
      <div className="top-locations">
        <h3>Top locations</h3>
        <ul>
          {stats?.top_locations?.map(([location, count]: [string, number]) => (
            <li key={location}>
              <span>{location}</span>
              <strong>{count}건</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function JobsTable({
  data,
  isLoading,
}: {
  data?: any;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <div className="glass-panel">로딩 중...</div>;
  }

  return (
    <section className="glass-panel jobs-panel">
      <header>
        <h2>공고 리스트</h2>
        <p>
          ({data?.counts?.recommended ?? 0} 추천 ·{" "}
          {data?.counts?.non_recommended ?? 0} 보류)
        </p>
      </header>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>공고명</th>
              <th>회사 · 위치</th>
              <th>스코어</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {data?.jobs?.map((job: any) => (
              <tr key={job.dashboard_key ?? job.url}>
                <td>
                  <a href={job.url} target="_blank" rel="noreferrer">
                    {job.title}
                  </a>
                  <p className="job-meta">{job.fit_tags?.join(" · ")}</p>
                </td>
                <td>
                  <strong>{job.company}</strong>
                  <div>{job.location}</div>
                </td>
                <td>
                  <span className="score-pill">{job.match_score}</span>
                  <small>{job.country}</small>
                </td>
                <td>
                  <span
                    className={`status-pill ${
                      job.qualifies ? "pill-recommended" : "pill-caution"
                    }`}
                  >
                    {job.qualifies ? "추천" : "보류"}
                  </span>
                  <div className="source-chip">{job.source_label}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecommendationsPanel({ data }: { data?: any }) {
  return (
    <section className="glass-panel recommendations-panel">
      <header>
        <h3>Top Recommendations</h3>
      </header>
      <div className="recommendations">
        {data?.recommendations?.map((job: any) => (
          <article key={job.dashboard_key ?? job.url}>
            <div>
              <p className="recommend-title">{job.title}</p>
              <small>{job.company}</small>
            </div>
            <span className="small-score">{job.match_score}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function NewsPanel({
  news,
  topics,
}: {
  news?: any[];
  topics?: any[];
}) {
  return (
    <section className="glass-panel news-panel">
      <header>
        <h3>News & Topics</h3>
      </header>
      <div className="news-grid">
        <div>
          <h4>Latest News</h4>
          <ul>
            {news?.slice(0, 5).map((item: any) => (
              <li key={item.url}>
                <a href={item.url} target="_blank" rel="noreferrer">
                  {item.title}
                </a>
                <small>{item.source_label}</small>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Topics</h4>
          <ul>
            {topics?.map((topic: any) => (
              <li key={topic.key}>
                <span>{topic.label_ko}</span>
                <strong>{topic.article_count}건</strong>
              </li>
            ))}
          </ul>
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
        limit: 40,
      }),
    keepPreviousData: true,
  });

  const recommendationQuery = useQuery({
    queryKey: ["recommendations"],
    queryFn: () => fetchRecommendations(),
  });

  const newsQuery = useQuery({
    queryKey: ["news"],
    queryFn: () => fetchNews(),
  });

  const topicsQuery = useQuery({
    queryKey: ["topics"],
    queryFn: () => fetchTopics(),
  });

  const playerQuery = useQuery({
    queryKey: ["player-mentions"],
    queryFn: () => fetchPlayerMentions(),
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
      <header className="glass-panel hero">
        <div>
          <h1>Job Watch</h1>
          <p>Glassmorphism 기반 실시간 대시보드 · TypeScript + FastAPI + Vite</p>
        </div>
        <div className="hero-badges">
          {countryCounts.map(([country, value]) => (
            <span key={country} className="status-pill">
              {country}: {value}
            </span>
          ))}
        </div>
      </header>

      <div className="layout-grid">
        <StatsPanel stats={statsQuery.data?.stats ?? statsQuery.data} />
        <FilterBar filters={filters} onChange={setFilters} />
        <JobsTable data={jobsQuery.data} isLoading={jobsQuery.isLoading} />
        <RecommendationsPanel data={recommendationQuery.data} />
        <NewsPanel news={newsQuery.data?.news} topics={topicsQuery.data?.topics} />
      </div>
    </div>
  );
}

export default App;
