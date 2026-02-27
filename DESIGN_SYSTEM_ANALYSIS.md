# OGENTI Design System — Complete Analysis Report

> 전체 랜딩 페이지 + 앱 내부 TSX 15개 파일에서 추출한 디자인 시스템 분석

---

## 1. Color System

### 1.1 Landing Page (CSS Variables)
```
--black:        #000000     ← 페이지 배경
--bg-dark:      #050505     ← 사용 빈도 낮음
--bg-card:      #080808     ← 카드 배경 (핵심)
--bg-elevated:  #0e0e0e     ← hover / 강조 배경
--border:       #161616     ← 기본 보더, gap separator
--border-light: #1e1e1e     ← hover / 강조 보더
--text-primary: #e8e8e8     ← 본문 텍스트 (순백 X, 약간 dim)
--text-secondary: #707070   ← 서브 텍스트
--text-muted:   #454545     ← 라벨, 메타 정보
--accent:       #c0c0c0     ← 강조 (solution 라벨)
--accent-dim:   rgba(255,255,255,0.06) ← 미묘한 하이라이트
```

### 1.2 App (Tailwind Custom Colors)
```
bg-primary:     #000000     ← 메인 배경
bg-secondary:   #0a0a0a     ← 사이드바, 헤더, 카드
bg-tertiary:    #111111     ← 중간 레벨 배경
bg-elevated:    #1a1a1a     ← hover 배경, 스켈레톤
bg-hover:       #222222     ← 드롭다운 hover
bg-active:      #2a2a2a     ← active state

border-primary: #222222
border-secondary: #333333
border-focus:   #555555

text-primary:   #ffffff     ← 본문 (순백)
text-secondary: #a0a0a0     ← 서브 텍스트
text-tertiary:  #666666     ← muted 텍스트
text-inverse:   #000000     ← 밝은 배경 위 텍스트

accent:         #ffffff     ← 강조 = 순백
accent-hover:   #e0e0e0
accent-muted:   #333333

success:        #22c55e
warning:        #f59e0b
error:          #ef4444
info:           #3b82f6
```

### 1.3 App 내부 TSX에서 사용하는 가상 투명도 패턴
```
white/[0.01] ~ white/[0.06] → 배경 미묘한 밝기
white/[0.06] ~ white/[0.12] → 보더
white/10 ~ white/20          → 보더 hover
white/20 ~ white/50          → 부제목 텍스트
white/70 ~ white/90          → 주요 텍스트
```

### 1.4 Color Philosophy
- **절대 순백(#fff)을 배경 전체에 쓰지 않는다** — 텍스트와 작은 강조 요소에만 사용
- **배경은 0%(#000) → 2%(#050505) → 3%(#080808) → 6%(#0e0e0e) → 10%(#1a1a1a) 같은 1~3% 단위 미세 차이**
- **보더는 배경보다 살짝 밝되 "겨우 보이는" 수준**: #161616(9%), #1e1e1e(12%), #222222(13%)
- **의미 컬러(초록, 빨강, 노랑, 파랑)는 semantic 상태에만 사용**, 장식적으로 안 씀
- **골드/앰버(amber-400, amber-500)는 프리미엄 티어 전용**

---

## 2. Typography

### 2.1 Font Stack
```
sans:  'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif
mono:  'JetBrains Mono', 'Fira Code', monospace
```

### 2.2 Landing Page Type Scale
| Element | Size | Weight | Tracking | Line-height |
|---------|------|--------|----------|-------------|
| Hero h1 | clamp(44px, 7vw, 88px) | 800 | -0.05em | 0.95 |
| Section title | clamp(28px, 4vw, 48px) | 700 | -0.035em | 1.1 |
| Section label | 10px | 600 | 0.2em | — |
| Hero subtitle | clamp(15px, 1.8vw, 18px) | 300 | — | 1.75 |
| Card heading | 14-18px | 600 | -0.01~-0.02em | — |
| Card body | 12-13px | 400 | — | 1.75 |
| Nav links | 12px | 400 | 0.04em | — |
| Button text | 12-13px | 500-600 | -0.01~0.02em | — |
| Metric value | 32px | 700 | -0.04em | — |
| Metric label | 11px | 400 | 0.04em | — |
| Footer | 11px | 400 | 0.02em | — |

### 2.3 App TSX Type Scale
| Usage | Tailwind Class | Approx Size |
|-------|---------------|-------------|
| Page title | text-3xl font-bold | 30px / 700 |
| Section title | text-lg ~ text-2xl font-semibold | 18-24px / 600 |
| Card heading | text-sm font-medium/semibold | 14px / 500-600 |
| Body text | text-sm | 14px / 400 |
| Sub text | text-xs | 12px / 400 |
| Meta/badge | text-[10px] ~ text-[11px] | 10-11px / 500-700 |
| Micro badge | text-[8px] ~ text-[9px] | 8-9px / 700 |

### 2.4 Typography Rules
- **제목: tight tracking (-0.03 ~ -0.05em)** → 시각적 응축감
- **라벨/메타: wide tracking (+0.04 ~ +0.25em) + uppercase** → 작은 글씨를 격식있게
- **본문: 300-400 weight** → 가벼운 느낌
- **gradient text**: 제목에만, `bg-gradient-to-b from-white to-white/40` (또는 `from-#e0e0e0 to-#555`)

---

## 3. Spacing System

### 3.1 Landing Page
```
Section padding:       140px top/bottom, 48px sides
Hero padding:          140px top, 100px bottom, 24px sides
Card internal:         44-52px padding (넉넉함)
Card heading gap:      20-24px margin-bottom
Grid gap:              1px (separator 기법)
Hero badge → h1:       56px
h1 → subtitle:         36px
Subtitle → buttons:    56px
Section label → title: 20px
Title → desc:          16px
Desc → grid:           56px
```

### 3.2 App TSX
```
Page padding:          px-6 py-12 (24px / 48px)
Card padding:          p-4 ~ p-6 (16-24px)
Gap between cards:     gap-4 ~ gap-6 (16-24px)
Icon boxes:            w-8 h-8 ~ w-12 h-12
Nav item:              px-3 py-2.5
Modal padding:         p-6
Form spacing:          space-y-4
```

### 3.3 Spacing Philosophy
- **Landing: 대담한 여백** — 140px 섹션 패딩, 56px 요소 간격
- **App: 실용적 여백** — 16-24px 카드, 12-48px 페이지
- **두 곳 모두 `gap: 1px` separator 패턴 사용** (랜딩의 핵심 기법)

---

## 4. Border & Radius System

### 4.1 Landing Page
```
Cards/grids:     border-radius: 16px (rounded-2xl 근접)
Nav logo mark:   border-radius: 7px
Buttons:         border-radius: 8px
Code block:      border-radius: 14px
Badge (pill):    border-radius: 100px
Arch tags:       border-radius: 5px
SDK cmd:         border-radius: 6px
Nav cta:         border-radius: 6px
```

### 4.2 App TSX
```
rounded-lg:    8px   ← 기본 (버튼, nav items, badges)
rounded-xl:    12px  ← 중간 (search bar, icon boxes, pricing cards)
rounded-2xl:   16px  ← 큰 카드 (modal, bento cards)
rounded-3xl:   24px  ← 대형 CTA 카드
rounded-full:  50%   ← pill badges, avatars, dots
```

### 4.3 Border Style
- **1px solid** — 항상 1px, 두꺼운 보더 없음
- **보더 색상은 배경보다 약간만 밝게** (값 차이 3-5%)
- **hover 시 보더 밝아짐**: `#161616 → #1e1e1e` 또는 `border-primary → border-secondary`
- **focus 시**: `ring-1 ring-border-active` (매우 절제된 포커스)

---

## 5. Layout Patterns

### 5.1 Landing Page — Gap-1 Grid Separator
```css
.grid-container {
  display: grid;
  gap: 1px;                          /* ← 핵심 */
  background: var(--border);          /* 1px gap이 보더 색이 됨 */
  border: 1px solid var(--border);
  border-radius: 16px;
  overflow: hidden;
}
.grid-cell {
  background: var(--bg-card);          /* 셀이 카드 색 */
}
```
이 기법이 landing 전체에 사용됨: metrics, problem grid, steps, features, arch, download, sdk, pricing.

### 5.2 App — Flex/Grid with card utility
```
card:       bg-bg-secondary border border-border-primary rounded-xl
card-hover: hover:bg-bg-elevated hover:border-border-secondary transition-all
```

### 5.3 Common Max Widths
```
Landing: max-width: 860px (metrics), 1000px (대부분), 650px (section title)
App:     max-w-4xl (settings/detail), max-w-6xl (dashboard), max-w-7xl (marketplace)
```

---

## 6. Component Patterns

### 6.1 Buttons
| Variant | Landing | App (Tailwind) |
|---------|---------|----------------|
| Primary | `bg: #e8e8e8, color: #000, hover: #ccc` | `bg-white text-black hover:bg-gray-200` |
| Secondary | `border: #1e1e1e, color: #707070, hover: border-#3a3a3a` | `bg-bg-elevated border-border-primary hover:bg-bg-hover` |
| Ghost | — | `text-text-secondary hover:text-text-primary hover:bg-bg-elevated` |
| Danger | — | `bg-red-500/10 text-red-400 border-red-500/20` |
| Press effect | `hover: translateY(-1px)` | `active:scale-[0.98]` |

**핵심**: Primary = 흰 배경 + 검정 텍스트. 이것이 유일한 "강한" 시각적 요소.

### 6.2 Cards
- **Landing**: `gap: 1px` separator 방식, 개별 보더 없음 (부모가 보더)
- **App**: 개별 `card` 클래스 with `border border-border-primary rounded-xl`
- **Hover**: Landing은 `bg: #080808 → #0e0e0e`, App은 `hover:bg-bg-elevated`

### 6.3 Badges / Labels
- **Section label**: 10-11px, uppercase, wide tracking, muted color
- **Status badge**: `text-[10px] px-2 py-0.5 rounded bg-bg-elevated text-text-tertiary`
- **Active badge**: `bg-white text-black` (반전)
- **Pill**: `rounded-full px-2.5 py-1`

### 6.4 Icons
- **Library**: Lucide React
- **Sizes**: 12-14px (inline/badge), 16-18px (nav/button), 20px (feature), 28px (tier icon), 32px (empty state hero)
- **Color**: 항상 `text-text-tertiary` 또는 `text-white/20~40`, hover 시 밝아짐
- **Icon box**: `w-10~12 h-10~12 rounded-xl bg-white/[0.05] border border-white/[0.08]`

### 6.5 Dropdowns / Menus
- `bg-bg-elevated border-border-primary rounded-xl shadow-2xl animate-fade-in`
- Items: `px-4 py-2~3 hover:bg-bg-hover transition-colors`
- Divider: `border-b border-border-primary`

### 6.6 Forms
- Label: `text-xs font-medium text-text-secondary mb-1.5`
- Input: `input-field` utility (bg-bg-secondary + border + rounded-lg + text-sm)
- Help text: `text-[11px] text-text-tertiary mt-1`

### 6.7 Loading / Empty States
- Spinner: `w-10 h-10`, double ring (border trick), `animate-spin`
- Skeleton: `bg-bg-elevated rounded animate-pulse`, 다양한 width
- Empty: centered, icon + title + description + action button

### 6.8 Toggle Switch
- Track: `w-10~12 h-5~6 rounded-full`
- On: `bg-white` track + `bg-black` knob
- Off: `bg-bg-elevated border border-border-primary` track + `bg-text-tertiary` knob

---

## 7. Animation & Interaction

### 7.1 Transitions
```
transition-colors           ← 가장 흔함 (보더, 텍스트, 배경 컬러만)
transition-all duration-150 ← 버튼 (빠른)
transition-all duration-300 ← 카드 호버 (자연스러운)
transition-all duration-700 ← 스크롤 fade-in (느린, 우아한)
```

### 7.2 Animations
```
fadeIn:      opacity 0→1, 0.2s
slideUp:     translateY(8px)→0 + opacity 0→1, 0.3s
pulseGentle: scale 1→1.02→1, 2s infinite
animate-spin: 로더
animate-pulse: 스켈레톤, live dot
pulse-dot:   opacity 1→0.3→1, 2.5s infinite (landing)
```

### 7.3 Scroll Animations (Landing + App page.tsx)
- **IntersectionObserver with threshold 0.15~0.3**
- `opacity: 0; translateY(8~30px)` → `opacity: 1; translateY(0)`
- Stagger delay: `index * 50~120ms`
- Easing: `cubic-bezier(0.16, 1, 0.3, 1)` (landing), standard ease (app)

### 7.4 Hover Effects
```
버튼:     translateY(-1px) + box-shadow (landing) / scale(0.98) active (app)
카드:     bg 밝아짐 + border 밝아짐
아이콘:   color 밝아짐 (white/20 → white/50)
이미지:   scale(1.05) on group-hover
Arrow →:  translateX(0.5px~3px) on group-hover
```

### 7.5 Motion (Framer Motion in App)
```
initial={{ opacity: 0, y: 10~20 }}
animate={{ opacity: 1, y: 0 }}
transition={{ delay: index * 0.05, duration: 0.3 }}
```

---

## 8. Design Sensibility (디자인 감성)

### 8.1 Core Identity
- **Ultra-dark monochrome** — 색상이 거의 없음. 흰색과 검정과 회색의 미세한 스펙트럼
- **Brutalist minimalism meets Swiss design** — 장식 제로, 그리드 엄격, 타이포그래피 중심
- **"거의 보이지 않는" 보더** — 구조를 암시하되 주장하지 않음
- **빛 = 정보 계층** — 밝을수록 중요. 순백(#fff)은 최상위 강조에만

### 8.2 What This Design DOES NOT Do
- ❌ 그라데이션 배경 (텍스트 그라데이션만 사용)
- ❌ 컬러풀한 accent (의미 있는 semantic color만)
- ❌ 둥근 그림자 / soft glow (sharp shadow 또는 아예 없음)
- ❌ 이모지
- ❌ 보더 2px 이상
- ❌ 밝은 면적의 색상 영역
- ❌ 장식적 일러스트레이션
- ❌ 과도한 애니메이션

### 8.3 Key Visual Techniques
1. **Gap-1 Separator Grid** — 보더 대신 부모 배경이 1px gap 통해 드러남
2. **Gradient Text** — 타이틀에 위→아래 white→gray 그라데이션
3. **Ambient Glow** — 매우 낮은 opacity (0.015~0.03)의 radial gradient + 큰 blur
4. **Monochrome Hierarchy** — 같은 #fff를 opacity로 계층화 (10%, 25%, 40%, 70%, 90%)
5. **Active State Inversion** — active/selected = `bg-white text-black` (유일한 강한 대비)
6. **Micro-typography**: 라벨은 10px uppercase tracking-widest, 숫자는 JetBrains Mono

### 8.4 Emotional Tone
- **차갑고 프로페셔널** → 감성적이지 않음
- **신뢰감** → 불필요한 장식이 없으므로 "이 제품은 기능에 집중한다"
- **개발자 지향** → 코드 블록, 모노스페이스, 터미널 미학
- **고급스러움** → 검은 배경 + 미세한 보더 + 절제된 타이포그래피 = 럭셔리 브랜드 감각

---

## 9. Landing ↔ App 일관성 분석

| 요소 | Landing | App | 일치도 |
|------|---------|-----|--------|
| 배경색 | #000 | #000000 | ✅ 완전 일치 |
| 카드 배경 | #080808 | #0a0a0a | ≈ 거의 일치 |
| 보더 색 | #161616 | #222222 | ≈ App이 살짝 밝음 |
| 텍스트 primary | #e8e8e8 | #ffffff | ⚠ App이 더 밝음 |
| 텍스트 secondary | #707070 | #a0a0a0 | ⚠ App이 더 밝음 |
| 텍스트 muted | #454545 | #666666 | ⚠ App이 더 밝음 |
| Font family | Inter + JetBrains Mono | Inter + JetBrains Mono | ✅ 일치 |
| Primary button | bg-#e8e8e8 text-#000 | bg-white text-black | ✅ 동일 원리 |
| Border radius | 16px (cards) / 8px (buttons) | rounded-2xl / rounded-lg | ✅ 일치 |
| Gap-1 separator | ✅ 전면 사용 | ❌ card 개별 보더 | ⚠ 다름 |
| Animation | IntersectionObserver fade-up | Framer Motion / Tailwind | ≈ 동일 효과 |

**발견**: Landing은 전체적으로 "더 어둡고 더 muted" — App은 "기능적으로 더 밝음". 이것은 의도적이며, landing = 분위기, app = 가독성.

---

## 10. Download Page 재생성을 위한 핵심 규칙

1. **배경은 #000, 카드 배경은 #080808**
2. **gap: 1px separator grid 기법 사용** — landing의 모든 섹션이 이것을 씀
3. **border-radius: 16px** (카드), **8px** (버튼/입력)
4. **보더 색: #161616** (landing 톤), hover 시 #1e1e1e
5. **Primary button: bg #e8e8e8 + color #000 + font-weight 600 + tracking -0.01em**
6. **Section label: 10px uppercase tracking 0.2em color #454545**
7. **제목: clamp(28px, 4vw, 48px) weight 700 tracking -0.035em**
8. **본문: 13px weight 400 color #707070 line-height 1.75**
9. **값/숫자: JetBrains Mono weight 500-700**
10. **SVG 아이콘만 사용** (stroke: var(--text-secondary), fill: none, stroke-width: 1.5)
11. **fade-up 스크롤 애니메이션** (IntersectionObserver, opacity+translateY)
12. **hover: 배경 #080808→#0e0e0e, 전환 0.3s**
13. **절대 새 색상이나 그라데이션 배경을 만들지 않는다**
14. **모든 텍스트와 구조는 바닥부터 1% 단위로 밝기 차이를 줘서 계층 구분**

---

*End of Analysis — Generated from landing/index.html (725 lines) + 15 TSX components (3744 lines)*
