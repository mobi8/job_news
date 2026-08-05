# `config/collection_sources.yaml` 검색 전략 감사 (Phase 1 — 분석만)

대상 repo: `mobi8/job_news` (main, 2026-08-02 기준 clone)
읽은 파일: `config/collection_sources.yaml`(전체 2007줄), `config/README.md`(전체), `src/utils/collection_config.py`(URL builder / target·keyword group / selector / count 관련 함수). 그 외 파일은 소스 사용 여부 확인 목적으로 grep만 수행 (`google_uae`, `telegram_channels`, `linkedin_post_spot` 등 6개 식별자).
**파일 수정 없음. 분석만 수행.**

---

## 0. 요약 스코어카드

| 항목 | 수치 |
|---|---|
| source_metadata 총 개수 | 25 |
| 실제 target에 연결된 source_metadata | 12 (48%) |
| **고아(orphaned) source_metadata** (target 없음) | **13 (52%)** |
| LinkedIn Jobs targets / 생성 URL | 19 / 19 |
| Indeed targets / 생성 URL | 1 target / 8 URL |
| Glassdoor 생성 URL | 7 |
| DrJobs 생성 URL | 7 (explicit "igaming" + keyword "igaming" 중복 제거됨) |
| JobSpy targets | 1 |
| Recruiters targets / watchlist 회사 수 | 4 target / 13 companies (**9개 회사는 target 없음**) |
| LinkedIn Posts plan 수 (locations×roles×leads) | 5×6×4 = **120** |
| LinkedIn Posts 실행 cap (`runtime.linkedin_posts.max_plans`) | **96** — 매 실행마다 약 24개(20%) plan 누락 |
| News RSS / Player RSS | 13 / 1 |
| enabled:false로 명시적으로 꺼진 target | 0 |

---

## A~F. Phase 1 분석

### A. Target 중복 분석

| Source | Target/Keyword A | Target/Keyword B | Overlap reason | Keep/Merge/Remove | Risk |
|---|---|---|---|---|---|
| linkedin_jobs (UAE) | `linkedin_uae_crypto_payment` (`crypto payment OR stablecoin payment OR crypto payments OR neobanking`) | `linkedin_uae_web3_wallet` (`web3 OR stablecoin OR crypto OR wallet OR neobanking`) | web3_wallet는 crypto_payment의 핵심어(stablecoin, crypto, neobanking)를 이미 OR로 포함. LinkedIn 키워드 매칭은 phrase가 아닌 OR 토큰 매칭에 가까워 사실상 겹치는 결과셋. | Merge — 두 target을 payments(결제 특화)와 wallet/custody(월렛 특화)로 명확히 분리해 겹치는 broad 단어(stablecoin, crypto, neobanking)를 한쪽에서만 유지 | Low — query 텍스트만 조정, selector/target_id 안 바뀜 |
| linkedin_jobs (UAE) | `linkedin_uae_custody_game` (`custody OR digital asset... OR game OR gaming`) | `linkedin_uae_mobile_game` / `linkedin_uae_game_studio` | custody_game 자체가 custody(우선순위#3)와 game(축소후보)을 한 target에 억지로 묶어놓음 → custody 검색인데 game 결과가 섞여 정밀도 저하, 동시에 game 관련 target과도 의미 중복 | Merge/Split — custody 전용 target으로 축소, game 부분 제거 | Medium — query 축소는 count를 줄이므로 안전하지만 custody 단독 결과량 감소 가능성 검증 필요 |
| linkedin_jobs (Remote) | `linkedin_emea_game_dev` | `linkedin_emea_game_studio` | 둘 다 순수 게임 개발/스튜디오 직무. `linkedin_uae_mobile_game`, `linkedin_uae_game_studio`와도 도메인 중복 (UAE ↔ EMEA 지역만 다름) | Remove 후보 — 사용자 우선순위에서 "일반 게임 개발자/순수 엔지니어링" 명시적 축소 대상 | High — target_id 제거는 DB에 tracked된 id 삭제이므로 회귀 위험 있음 (README "Common Mistakes" 경고). enabled:false로 우선 비활성화 권장 |
| linkedin_jobs vs indeed | `linkedin_uae_crypto_product` ↔ indeed `crypto_product` / `linkedin_uae_custody_game` ↔ indeed `custody_game` / `linkedin_uae_casino_resort` ↔ indeed `casino_resort` / `linkedin_uae_exchanges` ↔ indeed `exchanges` | query 문자열이 글자 그대로 동일 | source 목적이 다름 (LinkedIn=broad discovery, Indeed=local validation) → 진짜 중복 아님, 의도된 cross-check | **Keep** | None |
| linkedin_jobs (UAE) | `linkedin_uae_sales` (`sales manager OR business development OR account manager`) | 사용자 우선순위 #7 (iGaming account management)와 부분 중첩, 나머지는 "영업 전용 직무"로 명시적 축소 대상 | 전체 target이 아니라 query 중 "account manager" 일부만 유효, "sales manager/business development"는 generic sales로 노이즈 | Merge — "account manager"만 남기고 igaming_operations taxonomy로 이전, 나머지 제거 | Low |
| recruiters | 4개 target 모두 query에 `backlog` OR 절 포함 | `companies` watchlist 13개 중 4개만 실제 target 존재 (salt, discovered mena, stanley james, cander group, mint selection, ateca consulting, ap executive, blockchain talent, Hyphen Connect = 9개 고아) | 중복이라기보다 **누락** (watchlist에는 있지만 검색 target이 없음) | 아래 B/구조 표에서 별도 처리 | — |
| keyword_groups (compat layer) | `keyword_groups.indeed` (25개 키워드: operations manager, compliance, risk, sales... 포함) | `sources.indeed.targets[0].keyword_groups` (실제 8개 쿼리) | 이름은 같은 "indeed"지만 **서로 다른 키워드셋**이고, `keyword_groups.indeed`는 Python 어디에서도 소비되지 않음(grep 결과 0건 in `src/`) — 죽은 호환 레이어인데 실제 쿼리와 달라 보여서 편집 시 착각 유발 | Remove 후보(죽은 코드) 또는 실제 쿼리와 동기화 | Medium — YAML 코멘트는 "used by non-source-specific consumers"라 명시하지만 코드에서 미확인. 삭제 전 실제 consumer 존재 여부를 Python 전체에서 재확인 필요 |
| glassdoor / drjobs | `crypto`, `igaming`, `payment`, `wallet`, `digital asset`, `backlog` 등 거의 동일한 7개 키워드 셋을 각각 독립적으로 유지 | 두 소스 모두 "국지적 UAE 채용 사이트" 역할이라 목적이 유사 (LinkedIn/Indeed의 로컬 검증이 아니라 UAE 자체 채용 사이트) | 목적이 유사하지만 사이트가 다르므로 완전한 중복은 아님. 다만 두 리스트를 별도 유지·수정해야 하는 구조적 부담 | Keep, 단 공용 base keyword list로 구조 통일 권장 (구조 표 참고) | Low |

### B. Keyword 중복 분석 (개념별 경계)

| 개념 쌍 | 현재 상태 | 문제 | 권장 |
|---|---|---|---|
| crypto / web3 / blockchain / digital asset | 거의 모든 source에서 서로 다른 조합으로 반복 등장 (LinkedIn 6곳, Indeed 3곳, Glassdoor, DrJobs, Recruiters, Posts) | 우선순위 #1이므로 반복 자체는 타당하나, "crypto"만 단독으로 들어간 경우(`linkedin_emea_crypto`, drjobs `crypto`)는 generic crypto 채용(마케팅, 세일즈, 엔지니어 포함)까지 다 잡아 정밀도 낮음 | crypto 단독 broad query는 discovery(LinkedIn) 1곳만 유지, 나머지는 "operations/payment/custody" 등 role 한정어 결합 |
| payment / payments / fintech | payment(s)는 여러 곳에 등장하지만 "fintech" 단어 자체는 target query에는 거의 없음(RSS category에만 존재) | payments 관련 검색이 결제 "엔지니어"(`payments_engineer`)와 결제 "운영"을 구분하지 않음 | payments_engineer는 엔지니어링 직무이므로 사용자 축소 대상("순수 엔지니어링 직무")과 겹침 — payments operations/product 쪽으로 재정렬 |
| custody / wallet / settlement / treasury / operations | custody, wallet은 존재하지만 **settlement, treasury라는 단어 자체가 YAML 전체에 0건** | 사용자 우선순위 #3의 절반(settlement, treasury)이 검색어에 전혀 없음 | C. 누락 분석 참고, 신규 taxonomy `settlement_treasury` 필요 |
| product / product manager / TPM / delivery / integration | "product manager", "product owner"는 있지만 "technical product manager", "delivery manager", "integration manager"는 0건. "backlog"라는 매우 간접적인 대체 키워드로 product 신호를 잡으려 함 | backlog는 매우 광범위한 일반명사(업무 적체, 주문 backlog 등)라 정밀도 낮음. TPM/delivery/integration 같은 구체적 타이틀이 전혀 검색되지 않음 | backlog는 보조 신호로만 유지, TPM/delivery/integration 전용 쿼리 신설 |
| iGaming / casino / gaming / sportsbook | igaming은 잘 커버, "sportsbook"은 filters.focus_domain_terms에만 있고 실제 target query에는 0건 | sportsbook 특화 채용을 검색 쿼리 단에서 놓칠 가능성 | igaming 계열 쿼리에 sportsbook 추가 |
| PMO / project / program / transformation / strategic execution | 전부 0건 | 사용자 우선순위 #6 전체가 검색 전략에 없음 | 신규 taxonomy `pmo_transformation` |
| FX / CFD / brokerage / trading platform | 전부 0건 | 사용자 우선순위 #8 전체가 검색 전략에 없음 | 신규 taxonomy `brokerage_fx` |
| compliance / risk / AML / KYT | compliance·risk는 `keyword_groups.indeed`(죽은 레이어)와 `topics.news`(뉴스 분류용, 채용 검색과 무관)에만 존재. AML·KYT는 0건 | 실제 채용 검색 쿼리에는 compliance/risk/AML/KYT가 전혀 반영 안 됨 | 신규 taxonomy `compliance_risk` (crypto-adjacent 한정) |

### C. 직무 누락 분석

| Missing area | Why relevant to my career | Suggested keyword/query | Recommended sources | Priority |
|---|---|---|---|---|
| Settlement / Reconciliation | 우선순위 #3 핵심 | "settlement operations", "reconciliation analyst", "crypto settlement" | LinkedIn, Indeed | High |
| Treasury operations / Liquidity operations | 우선순위 #3 핵심 | "treasury operations", "liquidity operations", "digital asset treasury" | LinkedIn, Indeed | High |
| Technical Product Manager / Product Operations | 우선순위 #4 핵심, 현재 "backlog"라는 간접어로만 대체 | "technical product manager", "TPM crypto", "product operations manager" | LinkedIn, Indeed | High |
| Implementation Manager / Delivery Manager / Payment Integration | 우선순위 #5 핵심 | "implementation manager payments", "delivery manager fintech", "payment integration manager" | LinkedIn, Indeed | High |
| PMO / Program Manager / Transformation / Strategic Initiatives | 우선순위 #6 전체가 비어있음 | "PMO crypto", "program manager payments", "transformation lead fintech" | LinkedIn, Recruiters | High |
| Operational Risk / Controls / Vendor Management | 백오피스 운영직무와 밀접 | "operational risk crypto", "vendor management payments", "controls analyst" | LinkedIn, Indeed | Medium |
| Transaction Monitoring / KYT / Crypto Compliance Operations | crypto ops와 직결, 컴플라이언스 채용 급증 분야 | "transaction monitoring crypto", "KYT analyst", "crypto compliance operations" | LinkedIn, Indeed | Medium |
| Brokerage Payments / FX Payments / Trading Platform Operations | 우선순위 #8 전체가 비어있음 | "FX payment operations", "brokerage operations", "trading platform operations" | LinkedIn, Indeed | Medium |
| iGaming Account Manager / Partner Operations / Casino Operations | 우선순위 #7과 직결하나 현재 casino_resort 쿼리가 wynn/al marjan/IT product manager 등 엉뚱한 단어와 묶여있어 순수 iGaming ops 검색이 약함 | "igaming account manager", "partner operations igaming", "casino operations manager" | LinkedIn, Indeed, Glassdoor, DrJobs | Medium |
| Live Operations / Platform Operations (gaming, non-engineering) | 우선순위 #10, 단 엔지니어링/개발 직무는 명시적으로 제외해야 함 | "live operations manager", "platform operations gaming" (game developer/unity/unreal 등은 exclude) | LinkedIn (축소 비중) | Low |

### D. 지역 누락 및 과잉 분석

| Region | Current coverage | Gap | Recommendation | Priority |
|---|---|---|---|---|
| UAE — Dubai | LinkedIn Jobs 14/19 target이 UAE, 그중 10개는 `location: "Dubai, United Arab Emirates"`로 명시적 도시 타겟팅 | 없음 | 유지 | — |
| UAE — Abu Dhabi | 4개 UAE target이 `location: "United Arab Emirates"`(국가 단위)로만 설정, Abu Dhabi 전용 geo_id 타겟 없음. `filters.focus_location_terms`에는 "abu dhabi" 존재 | LinkedIn/Indeed에 Abu Dhabi 전용 geo_id target 부재 → 국가 단위 broad 검색에 의존 | Abu Dhabi 전용 LinkedIn target 1개 추가 검토 (geo_id 확보 필요) | Medium |
| Saudi Arabia | `posts_remote_mena`의 거대 OR 쿼리 문자열 안에 "Saudi" 한 단어로만 존재, `filters.remote_gcc_location_terms`에도 포함. 독립 target은 0개 | LinkedIn Jobs/Indeed에 Saudi 전용 target 없음 — GCC 최대 시장 중 하나가 사실상 미검색 | Saudi Arabia 전용 target 신설 검토 (사용자 우선순위엔 명시 안 됐지만 GCC/MENA Secondary 범주에 포함되는 핵심국) | Medium |
| GCC / MENA / EMEA Remote | `linkedin_emea_*` 4개 target + `posts_remote_mena` 1개 location으로 커버, geo_id 92000000(EMEA 광역) 사용 | 너무 넓음 — EMEA 전체(유럽+중동+아프리카)를 하나의 geo_id로 묶어 유럽 non-target 국가 결과도 섞임. 반대로 GCC 자체를 별도로 좁힌 target은 없음 | EMEA는 유지하되 GCC 전용(중동만) 좁은 target 1개 분리 검토 | Medium |
| Amsterdam / Netherlands | **LinkedIn Posts에만 존재**(`posts_amsterdam`, hiring-signal). LinkedIn Jobs·Indeed 어디에도 Amsterdam target 없음 | Secondary 우선순위 지역인데 실제 공고 검색(LinkedIn Jobs/Indeed) 경로가 전무, recruiter 게시물 신호에만 의존 | LinkedIn Jobs Amsterdam target 신설 | High |
| Australia | 마찬가지로 **LinkedIn Posts에만 존재**(`posts_australia`), Jobs/Indeed 없음 | 위와 동일 | LinkedIn Jobs Australia target 신설 | High |
| Malta | LinkedIn Posts에 `posts_malta`(전체 plan의 20% 비중, UAE와 동일 가중치) + source_metadata 3개(`indeed_malta`, `linkedin_malta`, `google_malta`)가 있으나 **전부 고아** — 실제 Jobs/Indeed target 없음 | 사용자는 Malta를 Optional로 분류했는데, LinkedIn Posts 가중치는 Primary(UAE)와 동일(24 plan) — 우선순위 대비 과잉 | Posts 비중을 낮추거나(예: role/lead 서브셋만), Optional 등급에 맞게 축소 | Medium |
| Georgia | source_metadata 3개(`indeed_georgia`, `linkedin_georgia`, `google_georgia`) 존재하지만 **실제 target 0개** — Posts에도 없음 | 사용자가 "축소 후보"로 지정했는데 이미 실질 검색 비중은 0%. 다만 고아 metadata가 "관리되고 있다"는 착시를 줌 | source_metadata 자체를 제거하거나 "deprecated" 표식 추가 | Low (정리 차원) |
| Singapore | Optional 우선순위. 현재 0건 — YAML 코멘트/예시(README 스타일 가이드)에만 "Singapore 추가 예시"로 등장, 실제 target 없음 | 신규 추가 시 실익 있음(우선순위 Optional이므로 소규모로) | LinkedIn Posts 또는 LinkedIn Jobs에 소규모 Singapore target 1개만 추가 검토 (count 증가 최소화) | Low |

### E. Source별 역할 분석

| Source | Current role | Problem | Recommended role | Query strategy |
|---|---|---|---|---|
| LinkedIn Jobs | Broad discovery (19 target, UAE+EMEA) | 역할은 맞으나 game/sales 등 저우선 도메인이 섞여 discovery 폭이 사용자 목표와 어긋남 | Broad discovery 유지, 단 taxonomy를 우선순위 1~9 중심으로 재배치, 10(gaming_operations)은 최소화 | 우선순위 taxonomy당 1~2개 target, OR 체인은 동일 taxonomy 내에서만 |
| Indeed | Local validation (LinkedIn과 동일 쿼리 다수 재사용) | 의도된 설계로 보이나, `keyword_groups.indeed`(죽은 호환 레이어)와 실제 target 쿼리가 달라 혼란 유발 | Local validation 유지 | LinkedIn과 1:1 대응 쿼리 세트 유지, 죽은 호환 레이어 정리 |
| Fixed job pages | Company-specific (Pragmatic Play, iGaming Recruitment 등 6개) | 전부 iGaming/카지노 채용 사이트 — 우선순위 1~6(crypto/payments/product/PMO)에 해당하는 company-specific 페이지가 전무 | 유지 + crypto/payments 특화 fixed page 있는지 조사(신규 추가는 Phase 2) | 변경 없음 (URL 하드코딩, 함부로 수정 금지) |
| LinkedIn Posts | Hiring signal / recruiter discovery (120 plan, 5 location×6 role×4 lead) | 역할은 명확하지만 `max_plans: 96` cap 때문에 매 실행 20%가 누락되고 어떤 조합이 빠지는지 불명확. game role이 1/6을 차지해 저우선 신호에 리소스 소모 | 유지, 단 role 6개를 taxonomy 10개 우선순위에 맞게 재배치, game 비중 축소 | leads×roles×locations 곱셈 구조 유지, role 축(현재 6개)만 재구성 |
| Recruiters | Agency/recruiter targeting (4 target, 13 watchlist) | watchlist 13개 중 9개(69%)가 실제 검색 target 없이 이름만 존재 — "관리되고 있다"는 착시 | Agency targeting 유지, watchlist와 target을 1:1로 맞추거나 미사용 9개 명시적 표식 | 회사별 keyword_query는 회사 전문분야(fintech/crypto/general)에 맞춰 세분화 |
| RSS / player feeds | Industry monitoring (13 news + 1 player) | 채용 검색이 아니라 산업 동향용이라 문제 없음. 다만 crypto/payments 전문 매체(우선순위1~2)가 igaming/game 매체(6개) 대비 적음(crypto 관련은 2개: intergame_crypto, finextra_crypto) | 유지, crypto/payments RSS 소스 추가 검토(카운트 증가 없이 game 계열 일부와 교체 검토 가능) | 변경 없음 (URL 하드코딩) |
| JobSpy | 라이브러리 기반 다중 사이트 집계, 현재 UAE Indeed 1개 target만 사용 | 역할이 사실상 Indeed의 재수집(keywords_from: indeed)이라 Indeed와 거의 동일한 결과 — 별도 역할 정의가 약함 | LinkedIn/Google 등 JobSpy가 지원하는 다른 사이트로 역할 분리하거나, "빠른 다중 사이트 스팟체크"로 명확화 | keywords_from을 indeed 외에 다른 소스로 다양화 검토 |

### F. 구조 통일성 분석

| Field/Concept | Current inconsistency | Proposed standard | Migration risk |
|---|---|---|---|
| source_metadata 활용 | 25개 중 13개(52%)가 어떤 target에도 연결 안 됨 (georgia×3, malta×3, google×3, telegram×3, linkedin_*_spot×2 등) | 모든 source_metadata는 최소 1개 이상의 실제 target/section에서 참조되어야 함. 미사용 항목은 `deprecated: true` 플래그 또는 별도 archive 섹션으로 분리 | Low — metadata 정리는 target/URL에 영향 없음. 단 Python 쪽에서 label/country 매핑으로 이 id들을 직접 참조하는지(google_uae 등은 확인됨) 재확인 필요 |
| target id naming | `linkedin_uae_*`, `indeed_uae`(단수, target 자체가 country), `drjobs_{idx}`(자동생성, 의미 없는 숫자) 등 규칙이 소스마다 다름 | `{source}_{region}_{taxonomy}` 형태로 통일 (예: `linkedin_uae_custody_wallet`) | Medium — id는 DB에 tracked되므로 이름 변경 시 과거 데이터 매핑 깨짐 (README 명시 경고) |
| target_group id ↔ keyword_group id | linkedin_jobs의 target_group.keyword_groups는 `crypto/payments/product/igaming` 4개 카테고리인데, indeed/glassdoor/drjobs/jobspy는 각각 다른 카테고리 조합(`crypto/payments/product`, `crypto/payments/product`, `crypto/payments/igaming`)을 사용 — 소스마다 카테고리 이름과 개수가 다름 | 전 소스 공통 taxonomy id(10개, 아래 표준안 참고)를 target_group.keyword_groups의 `keyword_group_ids`로 통일 | Medium — `_keyword_groups_for_selection` 등 selector 로직이 target_group.keyword_groups 유무에 의존하므로 구조 변경 시 selector 매칭 결과가 바뀔 수 있음 |
| country/region 규칙 | `country: "Remote"`(linkedin_emea, posts_remote_mena)와 `country: "Other"`(linkedin_post_spot, linkedin_job_spot)가 혼재. `region` 필드는 스키마에 정의돼 있지만(`SearchTarget.region`) YAML 어디서도 실제로 채워지지 않음(전부 country만 사용) | `country`(국가/광역) + `region`(도시/세부지역) 2단 필드를 실제로 분리해서 채우기, "Other"는 명확한 라벨(예: "Spot Check")로 교체 | Medium — region 필드가 비어있던 기존 동작에 의존하는 필터링 로직이 있는지 확인 필요 |
| aliases 규칙 | 일부 target_group은 `aliases: [linkedin_uae, united_arab_emirates]`처럼 스네이크케이스+국가풀네임 혼합, 일부는 빈 배열 `aliases: []` | alias는 항상 [snake_case id, 자연어 표기 1개] 2종 이상 유지, 빈 배열 금지 | Low |
| enabled 필드 사용 | target 레벨 `enabled`는 전부 `true`(0개 비활성) — 실질적으로 비활성화 메커니즘이 전혀 쓰이지 않고 있어 "낮은 우선순위 축소"를 표현할 방법이 현재 관례상 없음 | 저우선순위 taxonomy(game 등)는 삭제 대신 우선 `enabled: false`로 전환해 count를 줄이면서 회귀 위험을 낮춤 | Low — 이미 지원되는 필드, YAML 값만 변경 |
| keyword_groups (top-level compat) vs target-level keyword_groups | 이름이 같은 `keyword_groups`가 2곳에서 완전히 다른 스키마로 존재 (target-level: `[{id, query}]`, top-level: `{linkedin: [...], indeed: [...], google: [...]}`) 하고 top-level은 코드에서 미소비 확인 | 이름 충돌 해소: top-level을 `legacy_keyword_lists` 등으로 rename하거나 제거 | Medium — 실제 consumer가 없다고 grep으로 확인했으나 100% 확신은 Python 전체 재검토 필요 |
| linkedin_posts `max_plans` vs 실제 plan 수 | YAML 코멘트는 "120 plans"라고 명시하는데 `runtime.linkedin_posts.max_plans: 96`이라 항상 24개(20%) plan이 실행 시 잘림, 어떤 plan이 잘리는지 문서화 안 됨 | max_plans를 120으로 맞추거나(런타임 비용 검토 필요), 우선순위가 낮은 role/location 조합부터 명시적으로 제외해 realistic plan count를 문서화 | Medium — 실행 시간/리소스 트레이드오프 있음, count 변경은 Phase 2 승인 필요 |

---

## 표준 검색 Taxonomy 제안 (10개, 사용자 우선순위 1~10에 1:1 매핑)

각 taxonomy는 기존 target의 **query 재구성**을 의미하며, URL/plan 개수를 늘리지 않는 것을 원칙으로 함(저우선 taxonomy #10을 축소해 확보한 여유를 #4~#8 신규 taxonomy에 재배분).

| # | canonical id | label | aliases | recommended query terms | 제외할 generic terms | 적용 source | 적용 region | 대체 대상 |
|---|---|---|---|---|---|---|---|---|
| 1 | `digital_assets` | Digital Asset Operations | digital asset, digital assets, virtual assets | "digital asset operations", "digital asset custody", "virtual asset operations" | "digital asset management"(기업 DAM 소프트웨어), "AI", "software engineer" | LinkedIn, Indeed, Glassdoor | UAE(Dubai+AbuDhabi), Remote/MENA | `linkedin_uae_custody_game`(game 부분 제거), `linkedin_uae_crypto_product`(일부) |
| 2 | `payments` | Crypto Payments / Payment Operations | crypto payment, stablecoin payment, payment operations, PSP | "crypto payment operations", "stablecoin payments", "payment operations manager", "PSP operations" | "payments engineer"(순수 엔지니어링), 단독 "fintech" | LinkedIn, Indeed, Recruiters | UAE, Remote/MENA/EMEA | `linkedin_uae_crypto_payment`, indeed `payments` |
| 3 | `custody_wallet` | Wallet / Custody Operations | wallet operations, custody operations, exchange operations | "wallet operations", "custody operations", "digital asset custody" | "wallet developer", "smart contract engineer" | LinkedIn, Indeed | UAE, Remote | `linkedin_uae_wallet_ops`(유지), `linkedin_uae_web3_wallet`(일부) |
| 4 | `settlement_treasury` | Settlement / Treasury / Reconciliation | treasury ops, settlement, reconciliation, liquidity ops | "settlement operations", "treasury operations", "reconciliation analyst", "liquidity operations" | "treasury software"(제품명), 일반 "finance manager" | LinkedIn(신규), Indeed(신규) | UAE, Remote | 없음(**신규**) |
| 5 | `product_delivery` | Product / TPM / Delivery / Integration | TPM, product owner, implementation manager, delivery manager, payment integration | "technical product manager payments", "payment integration manager", "implementation manager fintech", "product manager crypto" | 단독 "product owner"/"product manager"(도메인 한정어 없이) | LinkedIn, Indeed | UAE, Remote/EMEA, Amsterdam, Australia | `linkedin_uae_crypto_product`(재구성), "backlog" 단독 키워드 |
| 6 | `pmo_transformation` | PMO / Strategic Execution / Transformation | program manager, PMO, strategic initiatives, transformation | "PMO crypto", "program manager payments", "transformation lead fintech", "strategic initiatives crypto" | 일반 "project manager"(건설/IT인프라) | LinkedIn(신규), Recruiters | UAE, Remote, Amsterdam | 없음(**신규**) |
| 7 | `igaming_operations` | iGaming Payments / Operations / Account Management | igaming payments, casino ops, partner ops, account manager | "igaming payment operations", "casino account manager", "igaming partner operations", "player operations" | 단독 "casino"(호스피탈리티/리조트 오검색), 단독 "gaming resort" | LinkedIn, Indeed, Glassdoor, DrJobs, RSS | UAE, Malta, Remote | `linkedin_uae_casino_resort`(재구성), indeed `casino_resort`, `linkedin_uae_sales`(account manager 부분만) |
| 8 | `brokerage_fx` | FX / CFD / Brokerage Payment Infrastructure | FX payments, CFD brokerage, trading platform ops | "FX payment operations", "brokerage operations", "CFD trading platform", "forex payment infrastructure" | 단독 "trader"(프론트오피스 트레이딩), "sales trader" | LinkedIn(신규), Indeed(신규) | UAE, Remote | 없음(**신규**) |
| 9 | `compliance_risk` | Compliance / Risk / AML / KYT (crypto ops 한정) | AML operations, KYT, crypto compliance | "crypto compliance operations", "KYT analyst", "transaction monitoring crypto", "AML operations digital asset" | 일반 법무/규제 카운슬, 은행권 "risk manager"(crypto 무관) | LinkedIn(신규), Indeed(신규) | UAE, Remote | `linkedin_uae_regulation`(확장) |
| 10 | `gaming_operations` | Gaming / Live Operations / Platform Operations (비-iGaming, 저우선) | live ops, platform ops | "live operations manager", "platform operations gaming" | "game developer", "unity", "unreal", "mobile game", "game designer", "game artist", "indie game" | LinkedIn(대폭 축소), RSS 모니터링만 | UAE(축소) | `linkedin_uae_mobile_game`(제거 후보), `linkedin_uae_game_studio`(제거 후보), `linkedin_emea_game_dev`(제거 후보), `linkedin_emea_game_studio`(제거 후보) |

---

## 정량 분석

(YAML 직접 파싱 기준 실측치. "추정"이라 표시된 항목만 근사치.)

- **source별 target 수**: job_pages 6, linkedin_jobs 19, indeed 1(target)/8(생성URL), glassdoor 0(target 개념 없음, keyword 7개), drjobs 0(keyword 7개+explicit 1개, dedup 후 7 URL), jobspy 1, recruiters 4, linkedin_posts 0(target 대신 location 5×role 6×lead 4 = 120 plan), news_feeds 13, player_feeds 1.
- **source별 생성 URL/plan 수**: linkedin_jobs 19, indeed 8, glassdoor 7, drjobs 7, jobspy 1(라이브러리 호출 1건, 내부적으로 8개 Indeed 키워드 재사용), linkedin_posts 120(정의상)/96(런타임 cap), recruiters 4, job_pages 6(고정), news_feeds 13, player_feeds 1. **합계(고정+생성, posts는 96 cap 기준) ≈ 173**.
- **region별 target 수**: UAE — linkedin_jobs 14, indeed 8(전량), jobspy 1, recruiters 4, posts 24(plan) = 소계 51. Remote/EMEA/MENA — linkedin_jobs 5, posts 24(plan) = 소계 29. Amsterdam — posts 24(plan)만. Australia — posts 24(plan)만. Malta — posts 24(plan)만. Georgia — 0. (Amsterdam/Australia/Malta/Georgia는 Jobs/Indeed 실검색 0)
- **keyword taxonomy별 target 수 (추정, LinkedIn+Indeed 쿼리 concept 매핑 기준)**: crypto/digital_asset/web3/stablecoin 계열 — LinkedIn 6~10곳(중복 세지 않고 concept당), Indeed 5곳. game/gaming 계열 — LinkedIn 8회 등장(target 19개 중 4개가 game 전용), Indeed 3회. payment 계열 — LinkedIn 3회, Indeed 1회. backlog(암묵적 product 신호) — LinkedIn 2, Indeed 1, Glassdoor 1, DrJobs 1, Recruiters 4, Posts 1(role) = 총 10곳. settlement/treasury/PMO/FX/brokerage/TPM/delivery — 전부 0.
- **유사 query 후보 수(중복 위험)**: 위 A표 기준 최소 6개 쌍/그룹 — (1) crypto_payment↔web3_wallet, (2) custody_game 내부 custody/game 혼합, (3) emea_game_dev↔emea_game_studio↔uae_mobile_game↔uae_game_studio(4개 상호 유사), (4) linkedin_uae_sales의 sales 부분, (5) keyword_groups.indeed(죽은 레이어)↔실제 indeed 쿼리, (6) recruiters 4개 target의 backlog 반복. **총 중복 가능성이 높은 target 수 ≈ 8~9개 (전체 19개 LinkedIn target의 약 42~47%, 추정)**.
- **현재 비활성(enabled:false) target 수**: 0 (전수 조사 결과 — job_pages, linkedin_jobs, indeed, jobspy, recruiters, linkedin_posts locations 전부 `enabled: true` 또는 필드 생략(기본 true)).
- **낮은 우선순위 region이 차지하는 비중**: LinkedIn Posts 120 plan 기준 Malta 24/120 = **20%**, Amsterdam+Australia 48/120 = **40%**(단, 이 둘은 사용자 Secondary 우선순위이므로 낮은 우선순위는 아님). Georgia는 0/120 = 0%(이미 사실상 축소 완료, metadata만 잔존). 순수 "낮은 우선순위+게임 엔지니어링" 관련 LinkedIn Jobs target 비중은 4/19 = **21%**.
- **고아 source_metadata 비중**: 13/25 = **52%** (정확히 계산됨, 추정 아님).
- **recruiters watchlist 미사용 비중**: 9/13 = **69%** (정확히 계산됨).

---

## 최종 질문 답변

**1. 현재 YAML은 내 취업 목표에 얼마나 잘 맞는가?**
10점 만점에 **5.5점**. 우선순위 1~3(digital asset ops, crypto payments, custody/wallet)은 어느 정도 커버되지만 "operations" 한정어가 약해 generic crypto 결과가 섞임. 우선순위 4~6(TPM/delivery/PMO)과 8(FX/brokerage)은 검색어가 사실상 전무하고, 지역 커버리지는 Amsterdam/Australia가 실제 채용 검색이 아닌 recruiter-post 신호에만 의존한다는 점에서 구조적 공백이 크다.

**2. 가장 큰 중복 5개는 무엇인가?**
① `linkedin_uae_crypto_payment` ↔ `linkedin_uae_web3_wallet` (broad term 상호 포함), ② `linkedin_uae_custody_game` 내부의 custody/game 혼합, ③ game 계열 4개 target 상호 중복(`emea_game_dev`, `emea_game_studio`, `uae_mobile_game`, `uae_game_studio`), ④ `keyword_groups.indeed`(죽은 호환 레이어) vs 실제 indeed target 쿼리 divergence, ⑤ recruiters 4개 target에 반복되는 "backlog" OR 절.

**3. 가장 중요한 누락 10개는 무엇인가?**
settlement operations, treasury operations, technical product manager, delivery/implementation manager, PMO/program manager, transformation/strategic initiatives, FX/CFD/brokerage operations, trading platform operations, transaction monitoring/KYT/crypto compliance operations, Amsterdam·Australia의 실제 Jobs/Indeed target(현재 hiring-post 신호뿐).

**4. 제거 또는 축소해야 할 target은 무엇인가?**
`linkedin_uae_mobile_game`, `linkedin_uae_game_studio`, `linkedin_emea_game_dev`, `linkedin_emea_game_studio`(순수 게임 개발 — 4개), `linkedin_uae_sales`의 "sales manager OR business development" 부분(account manager는 유지), `linkedin_uae_payments_engineer`(순수 엔지니어링 성격 — 축소 또는 product/ops 관점으로 재작성). 우선 `enabled: false`로 시작하는 것을 권장(구조 F 참고, 삭제보다 회귀 위험 낮음).

**5. 추가해야 할 region / source / keyword는 무엇인가?**
Region — Amsterdam, Australia에 LinkedIn Jobs target 신설(현재 count 증가 없이 game 계열 target 축소분으로 상쇄 가능). Saudi Arabia, Abu Dhabi 전용 target 검토. Keyword — settlement, treasury, TPM, delivery, PMO, program manager, transformation, FX, brokerage, trading platform, transaction monitoring, KYT. Source 신설은 불필요 — 기존 LinkedIn/Indeed에 신규 taxonomy만 추가하면 됨.

**6. 현재 count를 유지하거나 줄이면서 품질을 올릴 수 있는가?**
가능. LinkedIn Jobs 19개 target 중 game 계열 4개(21%)를 축소/비활성화하면, 그 여유분을 settlement_treasury, pmo_transformation, brokerage_fx, product_delivery 등 신규 taxonomy로 재배분할 수 있어 **총 URL count를 19 이하로 유지**하면서 우선순위 1~9 커버리지를 크게 개선 가능.

**7. 가장 먼저 바꿔야 할 5개 항목은 무엇인가?**
① game 계열 4개 target을 `enabled: false`로 전환, ② 그 여유분으로 settlement_treasury / product_delivery(TPM) target 신설, ③ `linkedin_uae_custody_game`에서 game 부분 제거해 custody 전용으로 정제, ④ Amsterdam/Australia에 LinkedIn Jobs target 최소 1개씩 신설, ⑤ 고아 source_metadata 13개(52%)에 대한 처리 방침 결정(제거 또는 deprecated 표식).

**8. Phase 2에서 실제로 수정할 파일과 예상 변경량은?**
`config/collection_sources.yaml` 단일 파일. 예상 변경량: linkedin_jobs.targets 항목 약 6~8개 수정(query 재작성 4곳, enabled:false 전환 4곳), 신규 target 3~5개 추가(settlement_treasury, pmo_transformation, brokerage_fx, Amsterdam/Australia), source_metadata 정리 10~13개 항목. `src/utils/collection_config.py`는 스키마 자체를 바꾸지 않는 한 수정 불필요(순수 config 변경). 코드 변경이 필요한 경우는 target_group/keyword_group 스키마를 전 source 공통으로 통일할 때뿐이며, 이는 별도 승인 필요한 더 큰 변경.

**9. 변경 시 예상되는 회귀 위험은?**
낮음~중간. target `id` 삭제/변경은 DB tracked 값이라 위험(README 명시) — 따라서 삭제 대신 `enabled:false` 우선. query 텍스트 변경은 count에 영향 없이 결과셋만 바뀌므로 위험 낮음. `keyword_groups`(top-level) 제거는 실제 consumer가 0건으로 확인됐으나 100% 확신을 위해 Phase 2 착수 전 Python 전체 재grep 권장. `max_plans` 조정은 실행 시간/리소스에 영향을 주므로 별도 검증 필요.

**10. 한 번에 바꾸는 것이 좋은가, 단계별로 바꾸는 것이 좋은가?**
**단계별 권장.** 1단계: game 계열 target 4개 `enabled:false` 전환(위험 최소, 즉시 검증 가능) → `--check` 실행 및 결과 비교. 2단계: 신규 taxonomy(settlement_treasury, product_delivery, pmo_transformation) target 3~4개 추가, 1주 정도 실제 수집 결과 품질 확인. 3단계: Amsterdam/Australia target 추가 및 Malta LinkedIn Posts 비중 조정. 4단계(선택, 낮은 우선순위): 고아 source_metadata 정리, `keyword_groups`(top-level) 정리, id naming 통일 — 이는 구조적 리스크가 가장 크므로 마지막에.

---

**완료. 파일 수정/commit/push/PR 없음 — 분석 보고만 수행.**
