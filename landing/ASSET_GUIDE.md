# Landing Page Asset Guide

`landing/` 폴더의 이미지/비디오 에셋 추가 방법.

---

## 폴더 구조

```
landing/
├── index.html
└── assets/
    ├── images/     ← 이미지 여기
    └── videos/     ← 영상 여기
```

---

## 1. 갤러리 이미지 (Gallery 섹션)

6장 필요. 앱 스크린샷을 캡처해서 아래 이름으로 저장:

| 파일명 | 설명 | 권장 크기 |
|---|---|---|
| `gallery-1.png` | Agent Dashboard 화면 | 800×600 이상 |
| `gallery-2.png` | Community Feed 화면 | 800×600 이상 |
| `gallery-3.png` | Agent Chat 화면 | 800×600 이상 |
| `gallery-4.png` | Marketplace 화면 | 800×600 이상 |
| `gallery-5.png` | Collaboration Engine 화면 | 800×600 이상 |
| `gallery-6.png` | Credit Economy 화면 | 800×600 이상 |

### 적용 방법

`index.html`에서 각 갤러리 아이템의 placeholder를 이미지로 교체:

**변경 전:**
```html
<div class="gallery-item reveal">
  <!-- Replace with: <img src="assets/images/gallery-1.png" alt="Agent Dashboard" /> -->
  <div class="gallery-item-placeholder">
    <span>assets/images/gallery-1.png</span>
  </div>
  <div class="gallery-item-label">Agent Dashboard</div>
</div>
```

**변경 후:**
```html
<div class="gallery-item reveal">
  <img src="assets/images/gallery-1.png" alt="Agent Dashboard" />
  <div class="gallery-item-label">Agent Dashboard</div>
</div>
```

> gallery-1 ~ gallery-6까지 동일하게 반복.

---

## 2. 비디오 (Video 섹션)

| 파일명 | 설명 | 권장 |
|---|---|---|
| `demo.mp4` | 앱 시연 영상 | 1080p, 1~3분 |

### 적용 방법

`index.html`의 비디오 섹션에서 현재 placeholder div를 `<video>`로 교체:

**변경 전:**
```html
<div class="video-wrapper reveal reveal-delay-3">
  <div style="aspect-ratio: 16/9; background: #060606; position: relative;">
    <div class="video-play-overlay" id="video-play-overlay">
      ...
    </div>
  </div>
</div>
```

**변경 후:**
```html
<div class="video-wrapper reveal reveal-delay-3">
  <video controls poster="assets/images/video-poster.png">
    <source src="assets/videos/demo.mp4" type="video/mp4" />
  </video>
</div>
```

> `video-poster.png` (선택) — 영상 재생 전 표시할 썸네일. 없으면 `poster` 속성 제거.

---

## 3. OG Image (SNS 공유용)

| 파일명 | 설명 | 권장 크기 |
|---|---|---|
| `og-image.png` | SNS 공유 시 표시되는 이미지 | 1200×630 |

이미 `<meta property="og:image">` 태그에 설정돼 있음. 파일만 넣으면 됨.

---

## 빠른 체크리스트

```
[ ] assets/images/gallery-1.png
[ ] assets/images/gallery-2.png
[ ] assets/images/gallery-3.png
[ ] assets/images/gallery-4.png
[ ] assets/images/gallery-5.png
[ ] assets/images/gallery-6.png
[ ] assets/videos/demo.mp4
[ ] assets/images/video-poster.png  (선택)
[ ] assets/images/og-image.png      (선택)
```

---

## 팁

- **스크린샷 촬영**: 앱에서 각 화면 들어간 뒤 `Win + Shift + S` → 영역 선택 → PNG로 저장
- **영상 녹화**: OBS Studio 등으로 앱 시연 녹화 → MP4로 export
- **이미지 최적화**: [Squoosh](https://squoosh.app) 에서 WebP로 변환하면 로딩 빨라짐 (파일명 `.webp`로 변경 시 HTML도 같이 수정)
