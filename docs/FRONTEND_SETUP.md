# Frontend (Vite + TypeScript) Setup

이제 TypeScript 기반 Vite/React SPA가 `frontend/` 아래에 추가되었습니다. FastAPI 백엔드(`/api/*`)를 그대로 사용하면서 결과를 SPA에서 렌더링합니다.

## 로컬 실행
1. `cd frontend`
2. `npm install` (처음 실행 시 의존성을 설치하세요)
3. `npm run dev`
4. 브라우저에서 `http://127.0.0.1:5173`(기본 Vite 포트) 또는 설정한 프록시 주소로 접속하세요. Vite dev 서버는 `/api/*` 요청을 FastAPI(`http://127.0.0.1:8000`)로 프록시 처리합니다.

## 빌드/배포
- `npm run build`로 `dist/`를 생성할 수 있습니다.
- `npm run preview`로 정적 번들 테스트.
- 실제 운영은 `dist/`를 정적 서버(예: Nginx)에 올리고, FastAPI를 별도로 배포하면 됩니다.

## 주요 구조
- `src/App.tsx`: stats, jobs, recommendations, news를 모두 하나의 페이지에서 보여주는 메인 컴포넌트. 필터/버튼/Glassmorphism 스타일을 담당합니다.
- `src/lib/api.ts`: `/api` 엔드포인트를 axios + React Query로 호출하는 helper.
- `vite.config.ts`: `/api` 요청을 FastAPI로 프록시.

## 스타일
- Glassmorphism 효과를 주기 위해 `App.css`에서 반투명 배경, blur, border 등을 사용했습니다. 필요하면 추가로 Tailwind나 CSS 변수를 도입 가능합니다.

## 차례
1. FastAPI 서버(`uvicorn src.api.app:app --reload`)를 먼저 실행
2. SPA (`npm run dev`)를 띄워서 `/api` 데이터가 화면에 출력되는지 확인

추가로 뉴스/토픽/플레이어 모듈을 확장하고 싶은 경우 `App.tsx` 내 `useQuery` 를 추가하면 됩니다.
