"""
Agent Intelligence Module
화면 상태 분류, 자동 액션 해결, 스마트 프롬프트 빌드 등
엔진의 지능 레이어 담당
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import os


# ═══════════════════════════════════════════════════════════════════════
# BROWSER DETECTION HELPER (lightweight, no heavy imports)
# ═══════════════════════════════════════════════════════════════════════

_detected_browser: Optional[str] = None

def _detect_browser() -> str:
    """Detect installed browser. Returns 'chrome', 'msedge', or 'firefox'."""
    global _detected_browser
    if _detected_browser is not None:
        return _detected_browser
    for name, paths in [
        ("chrome", [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]),
        ("msedge", [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]),
        ("firefox", [
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        ]),
    ]:
        if any(os.path.exists(p) for p in paths):
            _detected_browser = name
            return name
    _detected_browser = "msedge"
    return "msedge"


# ═══════════════════════════════════════════════════════════════════════
# SCREEN STATE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

class ScreenState(Enum):
    """화면 상태 분류"""
    UNKNOWN = "unknown"
    DESKTOP = "desktop"
    BROWSER = "browser"
    BROWSER_SEARCH = "browser_search"
    BROWSER_PAGE = "browser_page"
    EDITOR = "editor"
    TERMINAL = "terminal"
    FILE_EXPLORER = "file_explorer"
    DIALOG = "dialog"
    LOGIN_FORM = "login_form"
    ERROR_SCREEN = "error_screen"
    LOADING = "loading"
    OGENTI_APP = "ogenti_app"


@dataclass
class ScreenAnalysis:
    """화면 분석 결과"""
    state: ScreenState
    confidence: float = 0.5
    active_app: str = ""
    visible_elements: List[str] = field(default_factory=list)
    suggested_action: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class ScreenStateClassifier:
    """화면 상태를 프로그래밍적으로 분류"""

    _BROWSER_KEYWORDS = [
        "chrome", "edge", "firefox", "brave", "opera", "safari",
        "browser", "- google", "google.com", "bing.com",
    ]
    _EDITOR_KEYWORDS = [
        "visual studio", "vscode", "vs code", "notepad", "sublime",
        "atom", "vim", "nano", "code -", "pycharm", "intellij",
    ]
    _TERMINAL_KEYWORDS = [
        "cmd", "powershell", "terminal", "command prompt",
        "windows terminal", "bash", "git bash",
    ]
    _FILE_EXPLORER_KEYWORDS = ["file explorer", "explorer.exe", "this pc", "내 pc"]
    _OGENTI_KEYWORDS = ["ogenti", "agent marketplace"]

    @staticmethod
    def classify(
        som_desc: str,
        active_window_hint: str,
        som_elements: list,
    ) -> ScreenAnalysis:
        """SoM 설명, 활성 윈도우 힌트, 요소 리스트로 화면 상태 분류"""
        combined = f"{som_desc} {active_window_hint}".lower()
        elements_text = " ".join(str(e) for e in som_elements).lower() if som_elements else ""
        all_text = f"{combined} {elements_text}"

        state = ScreenState.UNKNOWN
        confidence = 0.3
        details: Dict[str, Any] = {}

        # Ogenti 자체 앱 감지
        if any(kw in all_text for kw in ScreenStateClassifier._OGENTI_KEYWORDS):
            state = ScreenState.OGENTI_APP
            confidence = 0.9

        # 브라우저 감지
        elif any(kw in all_text for kw in ScreenStateClassifier._BROWSER_KEYWORDS):
            # 검색 vs 페이지 구분
            if any(kw in all_text for kw in ["search", "검색", "address bar", "url bar", "new tab"]):
                state = ScreenState.BROWSER_SEARCH
            else:
                state = ScreenState.BROWSER_PAGE
            confidence = 0.8

        # 에디터 감지
        elif any(kw in all_text for kw in ScreenStateClassifier._EDITOR_KEYWORDS):
            state = ScreenState.EDITOR
            confidence = 0.8

        # 터미널 감지
        elif any(kw in all_text for kw in ScreenStateClassifier._TERMINAL_KEYWORDS):
            state = ScreenState.TERMINAL
            confidence = 0.8

        # 파일 탐색기 감지
        elif any(kw in all_text for kw in ScreenStateClassifier._FILE_EXPLORER_KEYWORDS):
            state = ScreenState.FILE_EXPLORER
            confidence = 0.7

        # 다이얼로그/팝업 감지
        elif any(kw in all_text for kw in ["dialog", "popup", "alert", "confirm", "save as", "open file"]):
            state = ScreenState.DIALOG
            confidence = 0.7

        # 에러 화면 감지
        elif any(kw in all_text for kw in ["error", "exception", "crash", "not responding"]):
            state = ScreenState.ERROR_SCREEN
            confidence = 0.6

        # 로딩 감지
        elif any(kw in all_text for kw in ["loading", "please wait", "spinner"]):
            state = ScreenState.LOADING
            confidence = 0.6

        # 로그인 폼 감지
        elif any(kw in all_text for kw in ["login", "sign in", "password", "username"]):
            state = ScreenState.LOGIN_FORM
            confidence = 0.7

        # 데스크탑 (아무것도 매칭 안 되면)
        elif not som_desc.strip() and not active_window_hint.strip():
            state = ScreenState.DESKTOP
            confidence = 0.5

        visible = []
        if som_elements:
            visible = [str(e)[:50] for e in som_elements[:10]]

        return ScreenAnalysis(
            state=state,
            confidence=confidence,
            active_app=active_window_hint,
            visible_elements=visible,
            details=details,
        )


# ═══════════════════════════════════════════════════════════════════════
# AUTO ACTION RESOLVER
# ═══════════════════════════════════════════════════════════════════════

class AutoActionResolver:
    """사소한 결정을 LLM 호출 없이 자동 해결"""

    @staticmethod
    def resolve(
        screen_analysis: ScreenAnalysis,
        current_phase: str,
        task_type: str,
        action_history: Optional[List[dict]] = None,
    ) -> Optional[dict]:
        """
        화면 상태와 작업 유형에 기반해 자동 액션 반환.
        None이면 LLM 호출 필요.
        """
        state = screen_analysis.state
        history = action_history or []

        # Ogenti 앱이 보이면 → 엔진이 스크린샷 전에 이미 최소화 처리.
        # AutoActionResolver는 여기서 아무것도 하지 않음 (None 반환).
        # 자동 액션을 반환하면 무한루프의 원인이 됨.
        if state == ScreenState.OGENTI_APP:
            return None  # LLM에게 맡김 — 자동 액션 절대 금지

        # 로딩 중이면 잠시 대기
        if state == ScreenState.LOADING:
            return {
                "action": {"type": "wait", "params": {"seconds": 2}},
                "reason": "화면 로딩 중 — 잠시 대기",
            }

        # 데스크탑인데 작업 시작 단계 → 앱 열기 추천
        if state == ScreenState.DESKTOP and current_phase in ("init", "setup"):
            _browser = _detect_browser()
            app_map = {
                "research": _browser,
                "browsing": _browser,
                "coding": "cmd",
                "writing": "notepad",
            }
            app = app_map.get(task_type, _browser)
            return {
                "action": {"type": "open_app", "params": {"name": app}},
                "reason": f"데스크탑 상태에서 {task_type} 작업을 위해 {app} 열기",
            }

        # 에러 화면 → 닫기 시도
        if state == ScreenState.ERROR_SCREEN and len(history) > 0:
            last = history[-1]
            if last.get("screen_state") == ScreenState.ERROR_SCREEN.value:
                return {
                    "action": {"type": "hotkey", "params": {"keys": ["alt", "f4"]}},
                    "reason": "에러 화면 반복 감지 — 창 닫기 시도",
                }

        return None


# ═══════════════════════════════════════════════════════════════════════
# ACTION VALIDATOR
# ═══════════════════════════════════════════════════════════════════════

class ActionValidator:
    """액션 실행 전 유효성 검사 — 좌표 검증 포함"""

    @staticmethod
    def validate(
        action_type: str,
        action_params: dict,
        screen_analysis: ScreenAnalysis,
        task_type: str,
        action_history: List[dict],
        screen_width: int = 1920,
        screen_height: int = 1080,
    ) -> Optional[dict]:
        """
        액션을 실행 전에 검증.
        None → 통과, dict → block/fix 지시.
        좌표 검증: 범위 확인, 타입 확인, 정규화 좌표(0~1) 자동 변환.
        """
        state = screen_analysis.state

        # ── 좌표 검증 (click, double_click, right_click, move_mouse, drag) ──
        if action_type in ("click", "double_click", "right_click", "move_mouse",
                           "click_element", "double_click_element", "right_click_element"):
            x = action_params.get("x")
            y = action_params.get("y")
            if x is not None and y is not None:
                try:
                    x_val = float(x)
                    y_val = float(y)
                except (TypeError, ValueError):
                    return {
                        "block": True,
                        "reason": f"좌표 타입 오류: x={x}, y={y} (숫자여야 합니다)",
                    }

                # NOTE: 좌표 변환(0-1 normalized, Gemini 1000-unit 등)은
                # os_controller._resolve_coordinates()에서 일괄 처리.
                # ActionValidator는 좌표를 변환하지 않고 검증만 수행.

                # 화면 밖 좌표 경고 (극단적인 값)
                if x_val > screen_width * 1.5 or y_val > screen_height * 1.5:
                    return {
                        "block": True,
                        "reason": f"좌표가 화면 범위를 크게 초과: ({int(x_val)}, {int(y_val)}) — 화면 크기: {screen_width}x{screen_height}",
                    }

        # drag 좌표 검증
        if action_type == "drag":
            for coord_key, max_val in [("startX", screen_width), ("startY", screen_height),
                                        ("endX", screen_width), ("endY", screen_height)]:
                val = action_params.get(coord_key)
                if val is not None:
                    try:
                        float(val)
                    except (TypeError, ValueError):
                        return {
                            "block": True,
                            "reason": f"drag 좌표 타입 오류: {coord_key}={val}",
                        }

        # 리서치 작업인데 파일 탐색기를 열려고 하면 차단
        if task_type == "research" and action_type == "open_app":
            app_name = (action_params.get("name") or "").lower()
            if app_name in ("explorer", "file explorer"):
                return {
                    "block": True,
                    "reason": "리서치 작업에서 파일 탐색기 열기 차단 — 브라우저를 사용하세요",
                }

        # 같은 액션을 3번 연속 반복하면 차단
        if len(action_history) >= 3:
            recent = action_history[-3:]
            actions_str = [a.get("action", "") for a in recent]
            current_str = f"{action_type}({str(action_params)[:60]})"
            if all(a == current_str for a in actions_str):
                return {
                    "block": True,
                    "reason": f"같은 액션 3회 반복 감지: {action_type} — 다른 방법을 시도하세요",
                }

        # 브라우저에서 type_text로 URL 입력 시 → Ctrl+L 먼저 권장
        if (
            state in (ScreenState.BROWSER, ScreenState.BROWSER_PAGE)
            and action_type in ("type_text", "type_text_fast")
        ):
            text = action_params.get("text", "")
            if text.startswith("http") and len(action_history) > 0:
                last = action_history[-1].get("action", "")
                if "hotkey" not in last and "ctrl" not in last.lower():
                    return {
                        "fix": True,
                        "reason": "URL 입력 전 주소창 포커스 필요 — Ctrl+L 선행",
                        "action": {"type": "hotkey", "params": {"keys": ["ctrl", "l"]}},
                    }

        return None


# ═══════════════════════════════════════════════════════════════════════
# STUCK DETECTOR
# ═══════════════════════════════════════════════════════════════════════

class StuckDetector:
    """에이전트가 장기간 진행이 없을 때 감지"""

    @staticmethod
    def check(
        action_history: List[dict],
        screen_state: ScreenState,
        task_type: str,
        total_actions: int,
    ) -> Optional[dict]:
        """
        최근 히스토리를 분석하여 에이전트가 막혀있는지 판단.
        막혀 있으면 탈출 액션을 반환.
        
        ESCALATION STRATEGY (prevents infinite loops):
        - 1st stuck detection: Try Escape or Enter
        - After 3 consecutive auto-actions: Try Alt+F4
        - After 5 consecutive auto-actions: Open browser directly
        - After 8 consecutive auto-actions: Give up, let LLM decide
        """
        if len(action_history) < 3:
            return None

        # ── COUNT CONSECUTIVE AUTO-ACTIONS (prevents infinite loop) ──
        consecutive_auto = 0
        for entry in reversed(action_history):
            action_name = entry.get("action", "")
            if action_name.startswith("AUTO:"):
                consecutive_auto += 1
            else:
                break

        # ESCALATION: Too many auto-actions without progress
        if consecutive_auto >= 8:
            # Give up auto-actions entirely — let LLM think freely
            return None

        if consecutive_auto >= 5:
            # Try opening browser directly (may succeed where Escape failed)
            _browser = _detect_browser()
            return {
                "action": {"type": "open_app", "params": {"name": _browser}},
                "reason": f"자동 탈출 {consecutive_auto}회 실패 — {_browser} 직접 열기 시도",
            }

        if consecutive_auto >= 3:
            # Try Alt+F4 to close stuck window
            return {
                "action": {"type": "hotkey", "params": {"keys": ["alt", "f4"]}},
                "reason": f"자동 탈출 {consecutive_auto}회 실패 — Alt+F4로 창 닫기 시도",
            }

        # ── Alt+Tab 무한 루프 감지 (2회 연속이면 즉시 차단) ──
        recent3 = action_history[-3:]
        alt_tab_count = sum(
            1 for a in recent3
            if a.get("action", "") == "hotkey" and "alt" in str(a.get("params", "")).lower() and "tab" in str(a.get("params", "")).lower()
        )
        if alt_tab_count >= 2:
            _browser = _detect_browser()
            return {
                "action": {"type": "open_app", "params": {"name": _browser}},
                "reason": "Alt+Tab 무한 루프 감지! 직접 앱 열기로 전환",
            }

        recent = action_history[-4:] if len(action_history) >= 4 else action_history[-3:]

        # 최근 4개 모두 실패 → 직접 앱 열기 (Alt+Tab 아님!)
        if len(recent) >= 4 and all(not a.get("success", True) for a in recent):
            _browser = _detect_browser()
            return {
                "action": {"type": "open_app", "params": {"name": _browser}},
                "reason": "최근 4개 액션 모두 실패 — 브라우저 직접 열기",
            }

        # 많은 액션 실행 후에도 주요 진전 없음
        if total_actions > 20:
            last_10 = action_history[-10:]
            if last_10:
                success_rate = sum(
                    1 for a in last_10 if a.get("success", True)
                ) / len(last_10)
            else:
                success_rate = 1.0
            if success_rate < 0.3:
                return {
                    "action": {"type": "screenshot", "params": {}},
                    "reason": "많은 액션 후 낮은 성공률 — 스크린샷으로 현재 상태 재확인",
                }

        return None


# ═══════════════════════════════════════════════════════════════════════
# TASK PROGRESS TRACKER
# ═══════════════════════════════════════════════════════════════════════

class TaskPhase(Enum):
    """작업 진행 단계"""
    INIT = "init"
    SETUP = "setup"
    EXECUTION = "execution"
    VERIFICATION = "verification"
    COMPLETION = "completion"


@dataclass
class TaskState:
    """현재 작업 상태"""
    current_phase: TaskPhase = TaskPhase.INIT
    actions_in_phase: int = 0
    findings_count: int = 0
    total_actions: int = 0
    phase_history: List[str] = field(default_factory=list)


class TaskProgressTracker:
    """작업 진행 추적기"""

    # 작업 유형별 단계 정의
    TASK_PHASES = {
        "research": [TaskPhase.INIT, TaskPhase.SETUP, TaskPhase.EXECUTION, TaskPhase.VERIFICATION, TaskPhase.COMPLETION],
        "browsing": [TaskPhase.INIT, TaskPhase.SETUP, TaskPhase.EXECUTION, TaskPhase.COMPLETION],
        "coding": [TaskPhase.INIT, TaskPhase.SETUP, TaskPhase.EXECUTION, TaskPhase.VERIFICATION, TaskPhase.COMPLETION],
        "writing": [TaskPhase.INIT, TaskPhase.SETUP, TaskPhase.EXECUTION, TaskPhase.VERIFICATION, TaskPhase.COMPLETION],
    }

    # 단계 전환 조건 (최소 액션 수)
    PHASE_MIN_ACTIONS = {
        TaskPhase.INIT: 1,
        TaskPhase.SETUP: 2,
        TaskPhase.EXECUTION: 3,
        TaskPhase.VERIFICATION: 1,
    }

    def __init__(self, task_type: str):
        self.task_type = task_type
        self.phases = self.TASK_PHASES.get(task_type, self.TASK_PHASES["browsing"])
        self.state = TaskState(current_phase=self.phases[0])
        self.findings: List[str] = []
        self.urls_visited: List[str] = []
        self._phase_index = 0

    def get_total_phases(self) -> int:
        return len(self.phases)

    def update(
        self,
        action_type: str,
        action_params: dict,
        success: bool,
        screen_state: ScreenState,
    ):
        """액션 실행 후 상태 업데이트"""
        self.state.total_actions += 1
        self.state.actions_in_phase += 1

        # 단계 전환 로직
        min_actions = self.PHASE_MIN_ACTIONS.get(self.state.current_phase, 2)

        if self.state.actions_in_phase >= min_actions and success:
            self._try_advance_phase(action_type, screen_state)

    def _try_advance_phase(self, action_type: str, screen_state: ScreenState):
        """다음 단계로 전환 시도"""
        if self._phase_index >= len(self.phases) - 1:
            return

        current = self.state.current_phase

        # INIT → SETUP: 앱이 열렸을 때
        if current == TaskPhase.INIT and action_type in ("open_app", "focus_window"):
            self._advance()

        # SETUP → EXECUTION: 실제 작업 액션이 시작됐을 때
        elif current == TaskPhase.SETUP and action_type in (
            "click", "type_text", "type_text_fast", "run_command",
            "click_element", "scroll",
        ):
            self._advance()

        # EXECUTION → VERIFICATION: 충분한 액션 수행 후
        elif current == TaskPhase.EXECUTION and self.state.actions_in_phase >= 5:
            self._advance()

        # VERIFICATION → COMPLETION: 검증 완료
        elif current == TaskPhase.VERIFICATION and self.state.actions_in_phase >= 1:
            self._advance()

    def _advance(self):
        """다음 단계로 진행"""
        if self._phase_index < len(self.phases) - 1:
            self.state.phase_history.append(self.state.current_phase.value)
            self._phase_index += 1
            self.state.current_phase = self.phases[self._phase_index]
            self.state.actions_in_phase = 0

    def can_complete(self) -> Tuple[bool, str]:
        """완료 가능 여부 확인"""
        if self._phase_index < 2:
            return False, f"아직 {self.state.current_phase.value} 단계 — 최소 실행 단계까지 진행 필요"

        if self.state.total_actions < 3:
            return False, f"총 {self.state.total_actions}개 액션 실행 — 최소 3개 필요"

        if self.task_type == "research":
            if len(self.findings) < 3:
                return False, f"리서치 작업에 발견 사항 {len(self.findings)}개 — 최소 3개 필요 (FINDING: [fact] 태그로 기록)"
            if len(self.urls_visited) < 2:
                return False, f"URL {len(self.urls_visited)}개 방문 — 최소 2개 소스 필요"

        return True, "완료 가능"

    def add_finding(self, finding: str):
        """발견 사항 추가"""
        if finding and finding not in self.findings:
            self.findings.append(finding)
            self.state.findings_count = len(self.findings)

    def add_url(self, url: str):
        """방문 URL 추가"""
        if url and url not in self.urls_visited:
            self.urls_visited.append(url)

    def get_status_summary(self) -> str:
        """현재 진행 상태 요약"""
        return (
            f"phase={self.state.current_phase.value}, "
            f"actions={self.state.total_actions}, "
            f"findings={self.state.findings_count}, "
            f"urls={len(self.urls_visited)}, "
            f"phase_idx={self._phase_index}/{len(self.phases)}"
        )


# ═══════════════════════════════════════════════════════════════════════
# CONTEXT ACCUMULATOR
# ═══════════════════════════════════════════════════════════════════════

class ContextAccumulator:
    """작업 중 수집한 정보를 축적하여 컨텍스트 블록으로 변환"""

    def __init__(self, task_type: str, prompt: str):
        self.task_type = task_type
        self.original_prompt = prompt
        self.findings: List[str] = []
        self.urls_visited: List[str] = []
        self.content_summary: str = ""
        self.key_data: Dict[str, str] = {}

    def add_finding(self, finding: str):
        """발견 사항 추가"""
        if finding and finding not in self.findings:
            self.findings.append(finding)

    def add_url(self, url: str):
        """방문 URL 추가"""
        if url and url not in self.urls_visited:
            self.urls_visited.append(url)

    def update_content_summary(self, text: str):
        """작성된 내용 요약 업데이트"""
        if len(text) > len(self.content_summary):
            self.content_summary = text[:500]

    def build_context_block(self) -> str:
        """축적된 정보를 컨텍스트 블록으로 변환"""
        parts = ["📋 ACCUMULATED CONTEXT:"]

        if self.findings:
            parts.append("\n🔍 FINDINGS:")
            for i, f in enumerate(self.findings[-5:], 1):
                parts.append(f"  {i}. {f}")

        if self.urls_visited:
            parts.append("\n🌐 URLs VISITED:")
            for url in self.urls_visited[-5:]:
                parts.append(f"  - {url}")

        if self.content_summary:
            parts.append(f"\n📝 CONTENT WRITTEN: {self.content_summary[:200]}...")

        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# SMART PROMPT BUILDER
# ═══════════════════════════════════════════════════════════════════════

class SmartPromptBuilder:
    """화면 상태, 작업 진행, 컨텍스트를 종합하여 스마트 프롬프트 구축"""

    # 화면 상태별 힌트
    STATE_HINTS = {
        ScreenState.DESKTOP: "바탕화면이 보입니다. 작업에 필요한 앱을 열어야 합니다.",
        ScreenState.BROWSER_SEARCH: "브라우저 검색 화면입니다. 검색어를 입력하거나 URL을 방문하세요.",
        ScreenState.BROWSER_PAGE: "웹 페이지가 열려 있습니다. 내용을 확인하고 필요한 정보를 수집하세요.",
        ScreenState.EDITOR: "에디터가 열려 있습니다. 코드를 작성/수정하세요.",
        ScreenState.TERMINAL: "터미널이 열려 있습니다. 명령어를 실행하세요.",
        ScreenState.FILE_EXPLORER: "파일 탐색기가 열려 있습니다.",
        ScreenState.DIALOG: "대화 상자가 보입니다. 적절한 버튼을 클릭하세요.",
        ScreenState.ERROR_SCREEN: "에러 화면이 보입니다. 에러를 해결하거나 닫으세요.",
        ScreenState.LOADING: "로딩 중입니다. 잠시 기다리세요.",
        ScreenState.OGENTI_APP: "⚠ Ogenti 앱이 보입니다! 시스템이 자동으로 최소화합니다. open_app으로 필요한 앱을 직접 여세요.",
    }

    @staticmethod
    def build_step_prompt(
        screen_state: ScreenAnalysis,
        task_state: TaskState,
        tracker: TaskProgressTracker,
        context: ContextAccumulator,
        som_desc: str,
        action_history: List[dict],
        last_action_result: str = "",
    ) -> str:
        """지능형 단계 프롬프트 구축"""
        parts = []

        # 현재 화면 상태
        state_hint = SmartPromptBuilder.STATE_HINTS.get(
            screen_state.state, "화면 상태를 확인하세요."
        )
        parts.append(f"📍 SCREEN STATE: {screen_state.state.value} — {state_hint}")

        # SoM 설명
        if som_desc:
            parts.append(f"\n📋 VISIBLE ELEMENTS:\n{som_desc}")

        # 작업 진행 상태
        parts.append(
            f"\n📊 TASK PROGRESS: phase={task_state.current_phase.value}, "
            f"actions={task_state.total_actions}, findings={task_state.findings_count}"
        )

        # 마지막 액션 결과
        if last_action_result:
            parts.append(f"\n⚡ LAST RESULT: {last_action_result}")

        # 최근 액션 히스토리 (마지막 3개)
        if action_history:
            parts.append("\n📜 RECENT ACTIONS:")
            for a in action_history[-3:]:
                status = "✅" if a.get("success", True) else "❌"
                parts.append(f"  {status} Step {a.get('step', '?')}: {a.get('action', '?')}")

        # 단계별 지시
        phase = task_state.current_phase
        if phase == TaskPhase.INIT:
            parts.append("\n🎯 DIRECTIVE: 작업 환경을 설정하세요. 필요한 앱을 여세요.")
        elif phase == TaskPhase.SETUP:
            parts.append("\n🎯 DIRECTIVE: 작업 준비를 완료하세요. 필요한 페이지/파일을 여세요.")
        elif phase == TaskPhase.EXECUTION:
            parts.append("\n🎯 DIRECTIVE: 핵심 작업을 수행하세요.")
        elif phase == TaskPhase.VERIFICATION:
            parts.append("\n🎯 DIRECTIVE: 작업 결과를 검증하세요.")
        elif phase == TaskPhase.COMPLETION:
            parts.append("\n🎯 DIRECTIVE: 작업이 거의 완료되었습니다. 마무리하세요.")

        return "\n".join(parts)
