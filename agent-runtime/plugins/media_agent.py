"""
Media Agent — Domain: media
Slug: media_agent

Specialized plugin for media-domain agents (MediaForge, AudioCraft, VideoClip, ThumbnailGen, GifMaker).
Handles video/audio editing, format conversion, thumbnail generation, GIF creation,
and multimedia processing workflows.

Engines: Tier-dependent
Tools: media-domain specialized tools (video_trim, audio_extract, format_convert,
       thumbnail_generate, gif_capture, media_info, subtitle_add, watermark_apply)
"""

import asyncio
import json
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
    from core.planner_engine import PlannerEngine
except ImportError:
    AgentContext = None
    PlannerEngine = None

try:
    from core.learning_engine import LearningEngine
    HAS_LEARNING = True
except ImportError:
    HAS_LEARNING = False


MEDIA_WORKFLOW_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║              MEDIA AGENT — WORKFLOW GUIDE                           ║
╚══════════════════════════════════════════════════════════════════════╝

═══ VIDEO EDITING WORKFLOW ═══
  1. Open terminal (cmd/powershell)
  2. Check for ffmpeg: run_command "ffmpeg -version"
  3. If missing, install: run_command "winget install ffmpeg" or download
  4. Process video with ffmpeg commands:
     - Trim:    ffmpeg -i input.mp4 -ss 00:00:05 -to 00:00:30 -c copy output.mp4
     - Convert: ffmpeg -i input.avi -c:v libx264 -c:a aac output.mp4
     - Resize:  ffmpeg -i input.mp4 -vf scale=1280:720 output.mp4
     - Extract audio: ffmpeg -i input.mp4 -vn -acodec copy output.aac
     - Add watermark: ffmpeg -i input.mp4 -i logo.png -filter_complex "overlay=10:10" out.mp4
  5. Verify output: run_command "ffprobe output.mp4"

═══ AUDIO PROCESSING WORKFLOW ═══
  1. Check available tools (ffmpeg, audacity)
  2. Process audio:
     - Convert: ffmpeg -i input.wav -c:a libmp3lame -b:a 192k output.mp3
     - Trim: ffmpeg -i input.mp3 -ss 00:00:10 -to 00:02:30 output.mp3
     - Mix: ffmpeg -i voice.mp3 -i bg.mp3 -filter_complex amix=inputs=2 output.mp3
     - Volume: ffmpeg -i input.mp3 -filter:a "volume=1.5" output.mp3
  3. Verify: ffprobe output.mp3

═══ THUMBNAIL / IMAGE GENERATION ═══
  1. Open Paint or use ffmpeg for video thumbnails
  2. For video thumbnail: ffmpeg -i video.mp4 -ss 00:00:05 -vframes 1 thumb.png
  3. For custom: open Paint → draw → resize → save
  4. Batch: for loop with ffmpeg

═══ GIF CREATION ═══
  1. From video: ffmpeg -i input.mp4 -ss 0 -t 5 -vf "fps=10,scale=480:-1" output.gif
  2. From screen: use capture tools or ffmpeg screen recording
  3. Optimize: ffmpeg -i input.gif -vf "palettegen" palette.png
     then: ffmpeg -i input.gif -i palette.png -lavfi paletteuse output_opt.gif

═══ MEDIA INFO ═══
  ffprobe -v quiet -print_format json -show_format -show_streams input.mp4
"""


class MediaAgent(BasePlugin):
    name = "Media Agent"
    description = "Multimedia processing agent for video/audio editing, format conversion, thumbnail generation, and GIF creation."
    version = "4.2.0"
    slug = "media_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        media_sub = self._detect_media_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("media", "automation"):
            task_type = "media"

        await ctx.log(f"  Media sub-task: {media_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Media processing task ({media_sub}). Plan tool checks, processing, output verification."
            )
            plan_text = "\n\nMedia Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_media_strategy(media_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║          MEDIA AGENT — SPECIALIZED INSTRUCTIONS                     ║
╚══════════════════════════════════════════════════════════════════════╝

You are a MEDIA PROCESSING SPECIALIST. You handle video, audio, image, and
multimedia tasks using ffmpeg, Paint, and other tools available on Windows.

DETECTED TASK: {media_sub}

{strategy}

{MEDIA_WORKFLOW_GUIDE}

═══ MEDIA TOOLS ═══
  • video_trim         — Generates ffmpeg trim command
  • audio_extract      — Extracts audio from video
  • format_convert     — Converts between media formats  
  • thumbnail_generate — Creates thumbnails from video frames
  • gif_capture        — Creates GIF from video segment
  • media_info         — Gets media file metadata
  • subtitle_add       — Adds subtitles to video
  • watermark_apply    — Adds watermark overlay to video/image

═══ QUALITY STANDARDS ═══
  ✓ Always verify output file exists and has valid size
  ✓ Use appropriate codecs and quality settings
  ✓ Check input file before processing
  ✓ Report processing results with file sizes

  ✗ NEVER say complete without verifying output exists
  ✗ NEVER overwrite input files without backup
  ✗ NEVER use unsupported codecs
{plan_text}""")

        # Track media metrics
        files_processed = 0
        output_files = []
        tools_checked = False

        learning_engine = None
        if HAS_LEARNING:
            learning_engine = LearningEngine()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_initial_user_message(prompt, task_type)},
        ]

        action_failure_streak = 0
        consecutive_empty = 0

        await self._minimize_ogenti_window(ctx)

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step % 5 == 0:
                await ctx.log(f"  Step {step + 1}/{max_steps} — processed: {files_processed}, outputs: {len(output_files)}")

            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                max_h = self._tier_config.max_message_history
                messages = [messages[0]] + messages[-(max_h - 1):]

            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and files_processed > 0:
                    await ctx.log(f"✓ Media processing complete — {files_processed} files processed")
                    break
                else:
                    messages.append({"role": "user",
                                     "content": "❌ Process at least one media file before completing."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    messages.append({"role": "user",
                                     "content": "Open terminal and check ffmpeg:\nACTION: open_app\nPARAMS: {\"name\": \"cmd\"}"})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  🎬 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}': {json.dumps(result)[:500]}\nContinue..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track media-specific operations
                if atype == "run_command":
                    cmd = params.get("command", "")
                    if "ffmpeg" in cmd or "ffprobe" in cmd:
                        if "-i" in cmd and not cmd.strip().endswith("-version"):
                            files_processed += 1

                await ctx.log(f"  Step {step + 1}: {atype}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}"})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(1)

                await asyncio.sleep(0.5)
                await ctx.send_screenshot()

                if success:
                    action_failure_streak = 0
                    if HAS_LEARNING and learning_engine:
                        learning_engine.add_experience(
                            task_type=task_type, command=prompt, context={},
                            action=atype, result={"success": True}, confidence=0.7)
                    messages.append({"role": "user",
                                     "content": f"⚠ VERIFY: Did '{atype}' work? Check output.{step_context}"})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        await ctx.log(f"◆ {self.name} finished — {files_processed} files, {self._actions_executed} actions")

    # ── Media-specific helpers ──

    def _detect_media_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["video edit", "trim", "cut video", "merge video"]):
            return "video_editing"
        if any(k in p for k in ["audio", "podcast", "music", "sound", "mp3"]):
            return "audio_processing"
        if any(k in p for k in ["thumbnail", "preview image", "poster"]):
            return "thumbnail"
        if any(k in p for k in ["gif", "animation", "animated"]):
            return "gif_creation"
        if any(k in p for k in ["convert", "format", "transcode", "encode"]):
            return "format_conversion"
        if any(k in p for k in ["subtitle", "caption", "srt"]):
            return "subtitles"
        if any(k in p for k in ["watermark", "overlay", "logo"]):
            return "watermark"
        if any(k in p for k in ["record", "screen record", "capture"]):
            return "recording"
        return "general_media"

    def _get_media_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "video_editing": (
                "VIDEO EDITING STRATEGY:\n"
                "1. Open terminal, verify ffmpeg installed\n"
                "2. Analyze input video with ffprobe\n"
                "3. Determine edit operations (trim, merge, resize)\n"
                "4. Build ffmpeg command with proper parameters\n"
                "5. Execute and verify output file\n"
                "6. Check output quality and file size"
            ),
            "audio_processing": (
                "AUDIO PROCESSING STRATEGY:\n"
                "1. Check available audio tools (ffmpeg)\n"
                "2. Analyze input audio format and properties\n"
                "3. Apply processing: convert, trim, normalize, mix\n"
                "4. Use appropriate codec and bitrate settings\n"
                "5. Verify output quality"
            ),
            "thumbnail": (
                "THUMBNAIL GENERATION STRATEGY:\n"
                "1. If from video: use ffmpeg to extract frame at best timestamp\n"
                "2. If custom: open Paint, set canvas size, create design\n"
                "3. Apply text overlay or branding if needed\n"
                "4. Resize to target dimensions (1280x720 for YouTube)\n"
                "5. Save in PNG/JPEG format"
            ),
            "gif_creation": (
                "GIF CREATION STRATEGY:\n"
                "1. Determine source (video, screen, images)\n"
                "2. If from video: ffmpeg with fps=10, scale=480:-1\n"
                "3. Generate color palette first for quality\n"
                "4. Create GIF with palette optimization\n"
                "5. Check file size (target < 10MB)"
            ),
            "format_conversion": (
                "FORMAT CONVERSION STRATEGY:\n"
                "1. Identify input format and target format\n"
                "2. Select appropriate codec settings\n"
                "3. Execute conversion with ffmpeg\n"
                "4. Verify output formats and quality\n"
                "5. Compare file sizes"
            ),
        }
        return strategies.get(subtask, (
            "MEDIA PROCESSING:\n"
            "1. Identify the media type and desired operation\n"
            "2. Check for required tools (ffmpeg)\n"
            "3. Execute the processing\n"
            "4. Verify output quality"
        ))
