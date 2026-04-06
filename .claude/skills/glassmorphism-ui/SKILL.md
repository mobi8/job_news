---
name: glassmorphism-ui
description: "당신이 '글래스' 또는 '글래스모피즘'을 언급할 때마다, 모던하고 고급스러운 글래스모피즘 UI를 생성합니다. 카드, 테이블, 폼 등 어떤 컴포넌트든지 어두운 배경에 반투명한 글래스 효과와 세련된 그레이 톤으로 디자인합니다. 마진/패딩 최소화된 콤팩트한 레이아웃, 각진 경계선 스타일이 특징입니다. 즉시 사용 가능한 완성된 HTML/CSS 코드를 제공합니다."
---

## 글래스모피즘 UI 디자인 생성기

사용자가 '글래스' 또는 특정 UI 컴포넌트를 요청할 때, 즉시 사용 가능한 글래스모피즘 디자인 코드를 생성합니다.

### 핵심 디자인 원칙

**색상 팔레트:**
- 배경: 매우 어두운 그레이 (`#0f0f0f` ~ `#1a1a1a`)
- 글래스 효과: 반투명 흰색 백그라운드 (`rgba(255, 255, 255, 0.05)` ~ `rgba(255, 255, 255, 0.1)`)
- 테두리: 서브틀한 그레이 (`rgba(255, 255, 255, 0.1)` ~ `rgba(255, 255, 255, 0.15)`)
- 텍스트: 밝은 그레이 (`#e0e0e0` ~ `#f0f0f0`)
- 강조 텍스트: 거의 흰색 (`#ffffff`)

**글래스모피즘 특징:**
- Backdrop filter: `blur()` 효과 (8px ~ 12px)
- 반투명 레이어 (`rgba()` 사용)
- 세로 방향의 미묘한 그래디언트 (선택사항)
- 깔끔한 그림자 효과 (`box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3)`)

**레이아웃 특징:**
- 마진: 최소화 (컴포넌트 간 8px ~ 12px)
- 패딩: 콤팩트 (카드 내부 12px ~ 16px)
- 행 높이 (테이블): 32px ~ 36px (콤팩트)
- 경계선: 각진 느낌으로 매우 서브틀한 1px 또는 2px 경계선
- 모서리: `border-radius: 12px` ~ `16px` (너무 둥글지 않게)

### 컴포넌트별 템플릿

**카드 (Card)**
```html
<div class="glass-card">
  <!-- 내용 -->
</div>
```

CSS:
```css
.glass-card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  backdrop-filter: blur(10px);
  padding: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  color: #e0e0e0;
}
```

**테이블 (Table)**
```css
.glass-table {
  width: 100%;
  border-collapse: collapse;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.glass-table th {
  background: rgba(255, 255, 255, 0.08);
  padding: 12px;
  text-align: left;
  font-weight: 600;
  color: #f0f0f0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.glass-table td {
  padding: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  color: #e0e0e0;
}

.glass-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.05);
}
```

**버튼 (Button)**
```css
.glass-btn {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #f0f0f0;
  padding: 10px 20px;
  border-radius: 10px;
  cursor: pointer;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
}

.glass-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
```

**입력 필드 (Input)**
```css
.glass-input {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e0e0e0;
  padding: 10px 12px;
  border-radius: 10px;
  backdrop-filter: blur(10px);
}

.glass-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.glass-input:focus {
  outline: none;
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1);
}
```

### 코드 생성 가이드

사용자의 요청에 따라:

1. **완전한 HTML 구조** 제공 (<!DOCTYPE html> 포함)
2. **모든 CSS를 <style> 태그 내에 포함** (외부 파일 불필요)
3. **즉시 브라우저에서 열 수 있도록** 작성
4. 불필요한 주석은 최소화, 필요시 핵심 부분만 설명
5. 어두운 배경색을 항상 기본으로 설정 (`body { background-color: #0f0f0f; }`)

### 예시 구조

사용자가 "글래스 카드 3개 만들어줘"라고 요청하면:
- 완전한 HTML 페이지 반환
- 3개의 카드를 어두운 배경에 배치
- 글래스모피즘 효과 적용
- 즉시 사용 가능한 상태

사용자가 "글래스 테이블"을 요청하면:
- 샘플 데이터가 포함된 테이블
- 콤팩트한 마진/패딩
- 각진 경계선 스타일
- 호버 효과 포함

### 주의사항

- 항상 **완전한 HTML 페이지**를 제공 (스니펫 X)
- 색상 값은 정확히 지정 (미세한 조정으로 고급스러움 결정)
- 테이블은 **절대 너무 넓은 간격**을 주지 않기
- 글래스 효과는 과하지 않게 (`blur: 10px` 기준)
- 각 요소에 일관된 `border-radius` 사용 (12px ~ 16px)
