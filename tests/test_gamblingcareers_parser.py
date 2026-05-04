from utils.scrapers import parse_gamblingcareers_jobs
from utils.scoring import source_label


def test_parse_gamblingcareers_jobs_extracts_remote_cards():
    raw_html = """
    <html>
      <body>
        <article class="job-card">
          <div>Apr 14, 2026</div>
          <div>Full time</div>
          <a href="/job/1001/crm-manager-remote/">CRM Manager</a>
          <div>Hit Me Remote</div>
          <div>Own the strategy and lifecycle campaigns.</div>
        </article>
        <article class="job-card">
          <div>Feb 24, 2026</div>
          <div>Full time</div>
          <a href="/job/1002/senior-full-stack-engineer-remote/">Senior Full Stack Engineer</a>
          <div>Over99 Remote (Fully Remote)</div>
          <div>Scale the platform to millions of players.</div>
        </article>
      </body>
    </html>
    """

    jobs = parse_gamblingcareers_jobs(raw_html)

    assert len(jobs) == 2
    assert jobs[0].source == "gamblingcareers_remote"
    assert jobs[0].title == "CRM Manager"
    assert jobs[0].company == "Hit Me"
    assert jobs[0].location == "Remote"
    assert jobs[0].country == "Remote"
    assert jobs[0].remote is True
    assert source_label(jobs[0].source) == "GamblingCareers Remote"

    assert jobs[1].company == "Over99"
    assert jobs[1].location == "Remote (Fully Remote)"
    assert jobs[1].remote is True
