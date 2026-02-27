"""
Data Analysis Agent — Domain: data_analysis
Slug: data_analysis_agent

Specialized plugin for data-analysis-domain agents (Apex Analyst, DataForge, Scrappy, SQLMaster, ChartBuilder, CSVCleaner).
Handles dataset processing, statistical analysis, visualization, SQL queries,
data cleaning, and automated report generation.

Engines: Tier-dependent
Tools: data-analysis specialized tools (data_profile, stat_test, chart_suggest,
       sql_optimize, csv_clean, outlier_detect, correlation_matrix, report_template)
"""

import asyncio
import json
import re
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


DATA_ANALYSIS_WORKFLOW = """
╔══════════════════════════════════════════════════════════════════════╗
║          DATA ANALYSIS AGENT — WORKFLOW GUIDE                       ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PYTHON DATA ANALYSIS PIPELINE ═══

STEP 1 — SETUP:
  Open terminal → cd to working directory
  pip install pandas numpy matplotlib seaborn scipy openpyxl
  
STEP 2 — DATA LOADING (Python script):
  import pandas as pd
  import matplotlib.pyplot as plt
  import numpy as np
  
  # Load data
  df = pd.read_csv('data.csv')  # or .xlsx, .json
  print(df.shape)
  print(df.dtypes)
  print(df.describe())
  print(df.isnull().sum())

STEP 3 — DATA CLEANING:
  # Remove duplicates
  df = df.drop_duplicates()
  # Handle missing values
  df = df.fillna(df.median(numeric_only=True))  # or dropna()
  # Fix types
  df['date_col'] = pd.to_datetime(df['date_col'])
  # Remove outliers (IQR method)
  Q1 = df['col'].quantile(0.25)
  Q3 = df['col'].quantile(0.75)
  IQR = Q3 - Q1
  df = df[(df['col'] >= Q1 - 1.5*IQR) & (df['col'] <= Q3 + 1.5*IQR)]

STEP 4 — ANALYSIS:
  # Descriptive statistics
  print(df.describe())
  print(df.corr())
  # Group analysis
  grouped = df.groupby('category').agg({'value': ['mean', 'std', 'count']})
  # Time series
  df.set_index('date').resample('M').mean().plot()

STEP 5 — VISUALIZATION:
  # Bar chart
  df.groupby('category')['value'].mean().plot(kind='bar')
  plt.title('Average Value by Category')
  plt.tight_layout()
  plt.savefig('chart.png', dpi=150)
  
  # Scatter plot
  plt.scatter(df['x'], df['y'])
  plt.savefig('scatter.png')
  
  # Histogram
  df['value'].hist(bins=30)
  plt.savefig('histogram.png')

STEP 6 — REPORT:
  Open Notepad → write findings with:
  - Data overview (rows, columns, types)
  - Key statistics
  - Visualizations created
  - Insights and recommendations

═══ SQL ANALYSIS ═══
  For SQL tasks, write and execute queries:
  - Use sqlite3 for local databases
  - Explain query logic before running
  - Output results to CSV for analysis
  
═══ EXCEL WORKFLOW ═══
  For Excel tasks:
  - Open Excel via open_app
  - Enter data / formulas
  - Create charts
  - Save workbook
"""


class DataAnalysisAgent(BasePlugin):
    name = "Data Analysis Agent"
    description = "Data analysis agent for dataset processing, statistical analysis, visualization, SQL queries, and automated reporting."
    version = "4.2.0"
    slug = "data_analysis_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        data_sub = self._detect_data_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("data_analysis", "coding"):
            task_type = "data_analysis"

        await ctx.log(f"  Data sub-task: {data_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Data analysis task ({data_sub}). Plan: data loading, cleaning, analysis, visualization, report."
            )
            plan_text = "\n\nAnalysis Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_data_strategy(data_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║       DATA ANALYSIS AGENT — SPECIALIZED INSTRUCTIONS                ║
╚══════════════════════════════════════════════════════════════════════╝

You are a DATA ANALYSIS SPECIALIST. You process datasets, run statistics,
create visualizations, and generate analytical reports using Python, Excel, or SQL.

DETECTED TASK: {data_sub}

{strategy}

{DATA_ANALYSIS_WORKFLOW}

═══ DATA ANALYSIS TOOLS ═══
  • data_profile      — Generates quick data profile (types, nulls, stats)
  • stat_test         — Runs statistical test (t-test, chi-square, ANOVA)
  • chart_suggest     — Suggests best chart type for data
  • sql_optimize      — Optimizes SQL query
  • csv_clean         — Cleans CSV data (remove nulls, fix types, dedup)
  • outlier_detect    — Detects outliers using IQR/Z-score
  • correlation_matrix— Computes correlation matrix
  • report_template   — Generates analysis report template

═══ QUALITY STANDARDS ═══
  ✓ Always run actual analysis (not just describe what you would do)
  ✓ Verify data loaded correctly before analysis
  ✓ Create at least one visualization for visual tasks
  ✓ Save outputs (charts, reports, cleaned data)
  ✓ Include actual numbers and statistics in reports

  ✗ NEVER fabricate data or statistics
  ✗ NEVER skip data validation
  ✗ NEVER say complete without producing output
  ✗ NEVER create empty analysis files
{plan_text}""")

        # Track analysis metrics
        scripts_run = 0
        charts_created = 0
        data_loaded = False
        report_written = False

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
                await ctx.log(f"  Step {step + 1}/{max_steps} — scripts: {scripts_run}, charts: {charts_created}")

            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            if HAS_LEARNING and learning_engine:
                try:
                    adaptations = learning_engine.get_adaptations(task_type, {})
                    if adaptations:
                        messages.append({"role": "user",
                                         "content": "🧠 " + "\n".join(
                                             [f"• {a['recommendation']}" for a in adaptations[:3]])})
                except Exception:
                    pass

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                max_h = self._tier_config.max_message_history
                messages = [messages[0]] + messages[-(max_h - 1):]

            # Track analysis findings
            if "FINDING:" in response or "INSIGHT:" in response:
                if HAS_LEARNING and learning_engine:
                    learning_engine.add_experience(
                        task_type=task_type, command=prompt, context={},
                        action="extract_finding", result={"success": True}, confidence=0.8)

            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and scripts_run > 0:
                    await ctx.log(f"✓ Analysis complete — {scripts_run} scripts, {charts_created} charts")
                    break
                else:
                    messages.append({"role": "user",
                                     "content": "❌ Run actual analysis scripts before completing."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    messages.append({"role": "user",
                                     "content": "Start analysis! Open terminal:\nACTION: open_app\nPARAMS: {\"name\": \"cmd\"}"})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  📊 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}': {json.dumps(result)[:500]}\nContinue..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track data analysis operations
                if atype == "run_command":
                    cmd = params.get("command", "").lower()
                    if "python" in cmd and ".py" in cmd:
                        scripts_run += 1
                    if "savefig" in cmd or "to_csv" in cmd or "to_excel" in cmd:
                        charts_created += 1
                    if "pip install" in cmd:
                        pass  # dependency installation, don't count

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
                    
                    if atype == "run_command":
                        messages.append({"role": "user",
                                         "content": f"⚠ Check command output. If errors, fix and re-run. If chart saved, verify file.{step_context}"})
                    else:
                        messages.append({"role": "user",
                                         "content": f"⚠ VERIFY: Did '{atype}' work?{step_context}"})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        await ctx.log(f"◆ {self.name} finished — {scripts_run} scripts, {charts_created} charts, {self._actions_executed} actions")

    # ── Data analysis helpers ──

    def _detect_data_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["sql", "query", "database", "table"]):
            return "sql_analysis"
        if any(k in p for k in ["chart", "graph", "visualization", "plot", "dashboard"]):
            return "visualization"
        if any(k in p for k in ["clean", "preprocess", "transform", "wrangle"]):
            return "data_cleaning"
        if any(k in p for k in ["csv", "excel", "spreadsheet", "import"]):
            return "data_import"
        if any(k in p for k in ["statistic", "correlation", "regression", "hypothesis"]):
            return "statistical_analysis"
        if any(k in p for k in ["scrape", "extract", "crawl", "web data"]):
            return "data_extraction"
        if any(k in p for k in ["report", "summary", "insight"]):
            return "reporting"
        if any(k in p for k in ["machine learning", "model", "predict", "classify"]):
            return "ml_modeling"
        return "general_analysis"

    def _get_data_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "sql_analysis": (
                "SQL ANALYSIS STRATEGY:\n"
                "1. Create/connect to SQLite database\n"
                "2. Import data if needed: sqlite3 + .import\n"
                "3. Write optimized queries\n"
                "4. Execute and analyze results\n"
                "5. Export results to CSV\n"
                "6. Summarize findings"
            ),
            "visualization": (
                "VISUALIZATION STRATEGY:\n"
                "1. Load data with pandas\n"
                "2. Explore data structure and types\n"
                "3. Choose appropriate chart types:\n"
                "   - Trends over time → line chart\n"
                "   - Comparisons → bar chart\n"
                "   - Distributions → histogram\n"
                "   - Relationships → scatter plot\n"
                "   - Proportions → pie chart\n"
                "4. Create charts with matplotlib/seaborn\n"
                "5. Save as PNG with proper labels and titles"
            ),
            "data_cleaning": (
                "DATA CLEANING STRATEGY:\n"
                "1. Load raw data and inspect (shape, types, nulls)\n"
                "2. Remove duplicates\n"
                "3. Handle missing values (fill/drop based on context)\n"
                "4. Fix data types (dates, numbers, categories)\n"
                "5. Remove outliers if appropriate\n"
                "6. Standardize formats\n"
                "7. Save cleaned data to new file"
            ),
            "statistical_analysis": (
                "STATISTICAL ANALYSIS STRATEGY:\n"
                "1. Load data and compute descriptive stats\n"
                "2. Check data distribution (normality test)\n"
                "3. Run appropriate tests:\n"
                "   - Two groups → t-test\n"
                "   - Multiple groups → ANOVA\n"
                "   - Categorical → chi-square\n"
                "   - Relationship → correlation/regression\n"
                "4. Report p-values, effect sizes, confidence intervals\n"
                "5. Visualize results\n"
                "6. Write interpretation"
            ),
            "ml_modeling": (
                "ML MODELING STRATEGY:\n"
                "1. Load and explore data\n"
                "2. Feature engineering and selection\n"
                "3. Train/test split (80/20)\n"
                "4. Train model (sklearn)\n"
                "5. Evaluate: accuracy, precision, recall, F1\n"
                "6. Visualize results (confusion matrix, ROC)\n"
                "7. Report model performance"
            ),
        }
        return strategies.get(subtask, (
            "GENERAL DATA ANALYSIS:\n"
            "1. Load and inspect data\n"
            "2. Clean and prepare\n"
            "3. Analyze and compute statistics\n"
            "4. Visualize key findings\n"
            "5. Write summary report"
        ))
