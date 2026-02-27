import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function seed() {
  console.log('Seeding database...');

  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═
  // Users
  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═

  const adminPassword = await bcrypt.hash('admin123456', 12);
  const admin = await prisma.user.upsert({
    where: { email: 'admin@ogenti.app' },
    update: {},
    create: {
      email: 'admin@ogenti.app',
      username: 'admin',
      displayName: 'Platform Admin',
      passwordHash: adminPassword,
      role: 'ADMIN',
      bio: 'Platform administrator',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  const devPassword = await bcrypt.hash('developer123', 12);
  const nexus = await prisma.user.upsert({
    where: { email: 'nexus@ogenti.app' },
    update: {},
    create: {
      email: 'nexus@ogenti.app',
      username: 'nexus_labs',
      displayName: 'Nexus Labs',
      passwordHash: devPassword,
      role: 'DEVELOPER',
      bio: 'Building next-generation AI agents for developers and creators',
      website: 'https://nexuslabs.ai',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  const arcDev = await prisma.user.upsert({
    where: { email: 'arc@ogenti.app' },
    update: {},
    create: {
      email: 'arc@ogenti.app',
      username: 'arc_studio',
      displayName: 'Arc Studio',
      passwordHash: devPassword,
      role: 'DEVELOPER',
      bio: 'Precision AI tools for creative professionals',
      website: 'https://arcstudio.dev',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  const forgeAI = await prisma.user.upsert({
    where: { email: 'forge@ogenti.app' },
    update: {},
    create: {
      email: 'forge@ogenti.app',
      username: 'forge_ai',
      displayName: 'Forge AI',
      passwordHash: devPassword,
      role: 'DEVELOPER',
      bio: 'Enterprise-grade automation and analysis agents',
      website: 'https://forgeai.com',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  // Dev user matching the demo login credentials on the login page
  const devUser = await prisma.user.upsert({
    where: { email: 'dev@ogenti.app' },
    update: { passwordHash: devPassword },
    create: {
      email: 'dev@ogenti.app',
      username: 'dev',
      displayName: 'Developer',
      passwordHash: devPassword,
      role: 'DEVELOPER',
      bio: 'Default developer account',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  const userPassword = await bcrypt.hash('user123456', 12);
  const demoUser = await prisma.user.upsert({
    where: { email: 'user@ogenti.app' },
    update: {},
    create: {
      email: 'user@ogenti.app',
      username: 'demouser',
      displayName: 'Demo User',
      passwordHash: userPassword,
      role: 'USER',
      bio: 'AI enthusiast',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═
  // Agents -- 30 Agents, Extreme Tier Differentiation
  // =====================================================

  // Developer: Apex Labs (Tier S+ ultra-premium)
  const apexLabs = await prisma.user.upsert({
    where: { email: 'apex@ogenti.app' },
    update: {},
    create: {
      email: 'apex@ogenti.app',
      username: 'apex_labs',
      displayName: 'Apex Labs',
      passwordHash: devPassword,
      role: 'DEVELOPER',
      bio: 'Creators of the most advanced AI agents on the planet. Our agents use premium Vision, Planner, Memory, and Tool engines.',
      website: 'https://apexlabs.ai',
      emailVerified: true,
      settings: { create: {} },
    },
  });

  const agentsData = [
    // =====================================================
    //  TIER S+  (Premium $19.99-$29.99)
    //  Vision + Tool + Planner + Memory
    // =====================================================
    {
      name: 'Omniscient',
      slug: 'omniscient',
      description: 'Full-stack AI agent that handles coding, design, research, and automation tasks. Multi-engine architecture with vision, planning, and memory.',
      longDescription: `Omniscient is a versatile all-in-one AI agent. It combines multiple engine capabilities to handle diverse computer tasks.\n\n**Vision Engine** — Screen understanding, OCR text extraction, UI element detection, visual diff tracking.\n\n**Tool Engine** — Action chaining with retry logic, smart waits, macro recording/replay.\n\n**Planner Engine** — Multi-step planning with dependency graphs, adaptive replanning on failure.\n\n**Memory Engine** — Working + episodic memory. Remembers context across sessions.\n\n**Capabilities:**\n- Write and refactor code across multiple files\n- Create UI designs in Figma/browser\n- Research and compile reports from web sources\n- Automate repetitive workflows across applications\n\n**Supported tasks:**\n- Multi-file code editing and debugging\n- Design mockup creation\n- Web research with source compilation\n- Document and spreadsheet automation`,
      category: 'AUTOMATION',
      tier: 'S+',
      domain: 'automation',
      tags: JSON.stringify(['universal', 'premium', 'coding', 'design', 'research', 'automation']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'WINDOW_MANAGEMENT', 'BROWSER_CONTROL', 'APP_MANAGEMENT']),
      price: 29.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'WINDOW_MANAGEMENT', 'BROWSER_CONTROL']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 2140,
      rating: 4.8,
      reviewCount: 48,
    },
    {
      name: 'Apex Coder',
      slug: 'apex-coder',
      description: 'Advanced coding agent with autonomous debugging, multi-file refactoring, test execution, and support for 15+ programming languages.',
      longDescription: `Apex Coder is a powerful coding assistant that operates your IDE, terminal, and file system autonomously.\n\n**Core Features:**\n- Multi-file code editing with dependency awareness\n- Autonomous debugging via stack trace parsing\n- Test execution and iterative fixing\n- Git workflow: branch, commit, PR creation\n- Supports TypeScript, Python, Go, Rust, Java, C++, and more\n\n**How It Works:**\nDescribe a coding task in natural language. Apex Coder navigates your project, reads relevant files, makes changes, runs tests, and iterates until the task is complete.\n\n**Performance:**\n- Handles repos up to 500K+ lines\n- Multi-file refactoring with import resolution\n- Average bug fix time: under 2 minutes`,
      category: 'CODING',
      tier: 'S+',
      domain: 'coding',
      tags: JSON.stringify(['coding', 'premium', 'refactoring', 'debugging', 'testing', 'multi-language']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 24.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 3890,
      rating: 4.9,
      reviewCount: 76,
    },
    {
      name: 'Apex Designer',
      slug: 'apex-designer',
      description: 'UI/UX design agent that creates designs in Figma and browsers. Design systems, responsive layouts, component libraries, and prototypes.',
      longDescription: `Apex Designer operates design tools to create production-quality UI/UX designs.\n\n**Features:**\n- Vision Engine: Detects spacing, color schemes, reads mockup text\n- Tool Engine: Precise clicks in Figma, layer operations, auto-retries\n- Planner: wireframe > components > pages > review pipeline\n\n**What it creates:** Web/mobile designs, component design systems, responsive layouts, interactive prototypes, dark/light themes.\n\n**Supported tools:** Figma, Adobe XD, Sketch, browser CSS.\n\n**Output quality:** Design review pass rate 94%. Component reusability 89%.`,
      category: 'DESIGN',
      tier: 'S+',
      domain: 'design',
      tags: JSON.stringify(['design', 'premium', 'figma', 'ui-ux', 'design-system', 'prototyping']),
      capabilities: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'WINDOW_MANAGEMENT', 'FILE_SYSTEM', 'BROWSER_CONTROL']),
      price: 19.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'WINDOW_MANAGEMENT', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 1820,
      rating: 4.9,
      reviewCount: 34,
    },
    {
      name: 'Apex Analyst',
      slug: 'apex-analyst',
      description: 'Data analysis agent for datasets, statistical modeling, visualizations, and automated report generation in Python/Excel.',
      longDescription: `Apex Analyst automates data analysis workflows.\n\n**Capabilities:** CSV/JSON/Excel/SQL ingestion. Statistical tests, regression, classification, clustering. Visualizations via matplotlib, plotly, seaborn. Reports in PDF, HTML dashboards.\n\n**ML Pipeline:** Feature engineering, hyperparameter tuning, cross-validation, model explainability (SHAP).\n\n**Performance:** Handles large datasets with chunked processing. Report generation in 5-15 minutes.`,
      category: 'DATA_ANALYSIS',
      tier: 'S+',
      domain: 'data_analysis',
      tags: JSON.stringify(['data', 'premium', 'machine-learning', 'statistics', 'visualization']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'BROWSER_CONTROL']),
      price: 19.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 1560,
      rating: 4.8,
      reviewCount: 28,
    },
    {
      name: 'Apex Researcher',
      slug: 'apex-researcher',
      description: 'Deep web research agent with multi-source cross-referencing, credibility scoring, and structured report generation.',
      longDescription: `Apex Researcher automates deep research tasks.\n\n**Sources:** Google Scholar, arXiv, news sites, blogs, documentation, GitHub, forums.\n\n**Methods:** Multi-tab browsing, source credibility scoring, contradiction detection, structured report compilation.\n\n**Output:** Markdown reports with citations, executive summaries, SWOT analysis, comparison matrices.\n\n**Performance:** 50-200 sources per report. Average research time: 10-30 minutes.`,
      category: 'RESEARCH',
      tier: 'S+',
      domain: 'research',
      tags: JSON.stringify(['research', 'premium', 'academic', 'analysis', 'literature-review']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM', 'WINDOW_MANAGEMENT']),
      price: 19.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 2340,
      rating: 4.7,
      reviewCount: 41,
    },
    {
      name: 'Apex Ops',
      slug: 'apex-ops',
      description: 'DevOps automation agent for CI/CD pipelines, Docker, cloud deployment, server management, and infrastructure-as-code.',
      longDescription: `Apex Ops automates infrastructure and DevOps tasks.\n\n**Capabilities:**\n- Docker: container builds, compose, multi-stage\n- CI/CD: GitHub Actions, GitLab CI configuration\n- Cloud: AWS, GCP, Vercel deployment automation\n- IaC: Terraform, CloudFormation templates\n- Monitoring: Health checks, log analysis, alerting setup\n- Security: SSL certs, firewall rules, secrets management\n\n**Use cases:** Automated deployments, server setup, monitoring configuration, incident response.`,
      category: 'AUTOMATION',
      tier: 'S+',
      domain: 'automation',
      tags: JSON.stringify(['devops', 'premium', 'docker', 'cloud', 'ci-cd', 'infrastructure']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 19.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 1240,
      rating: 4.8,
      reviewCount: 22,
    },

    // =====================================================
    //  TIER S  (Pro $13-$19.99)
    // =====================================================
    {
      name: 'Sentinel Pro',
      slug: 'sentinel-pro',
      description: 'Enterprise full-stack coding agent with autonomous debugging, multi-repo refactoring, CI/CD pipeline management, and live test execution across any IDE.',
      longDescription: `Sentinel Pro is the most advanced coding agent available on the platform. It doesn't just write code ??it understands your entire project architecture, navigates complex codebases, and delivers production-ready changes.\n\n**Core Capabilities:**\n- Autonomous multi-file refactoring with dependency analysis\n- Real-time bug detection and auto-fix with stack trace parsing\n- Full terminal control: runs builds, tests, linters, formatters\n- Git workflow automation: branch, commit, PR creation\n- CI/CD pipeline debugging and configuration\n- Supports 15+ languages: TypeScript, Python, Rust, Go, Java, C++, etc.\n\n**How It Works:**\nSentinel Pro takes control of your IDE (VS Code, JetBrains, Vim), terminal, and file system. Describe what you want in natural language, and it will navigate your project, read relevant files, write code, run tests, and iterate until the task is complete.\n\n**Performance:**\n- Average task completion: 94.2% on SWE-bench\n- Handles repos up to 500K+ lines of code\n- Multi-agent chaining for complex architectural changes`,
      category: 'CODING',
      tier: 'S',
      domain: 'coding',
      tags: JSON.stringify(['coding', 'refactoring', 'debugging', 'testing', 'ci-cd', 'multi-language', 'enterprise', 'git']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 8420,
      rating: 4.9,
      reviewCount: 127,
    },
    {
      name: 'Architect',
      slug: 'architect',
      description: 'Full-stack application generator ??creates entire projects from a single prompt with database schemas, APIs, frontend, auth, and deployment configs.',
      longDescription: `Architect is a project-generation powerhouse. Give it a description of the application you want, and it will scaffold the entire project from scratch ??database to UI.\n\n**What Architect Builds:**\n- Database schemas (PostgreSQL, MySQL, SQLite, MongoDB)\n- REST and GraphQL API backends (Express, FastAPI, NestJS)\n- Frontend applications (React, Next.js, Vue, Svelte)\n- Authentication systems (JWT, OAuth, sessions)\n- Docker + docker-compose configurations\n- CI/CD pipelines (GitHub Actions, GitLab CI)\n- README, API docs, and test suites\n\n**Example Prompt:**\n"Build a SaaS project management tool with team workspaces, Kanban boards, real-time collaboration, Stripe billing, and a Next.js frontend with Tailwind."\n\nArchitect will create 50+ files across the full stack, configure all dependencies, and produce a working application you can run immediately.\n\n**Performance:**\n- Generates 30-80 files per project\n- Supports 12 tech stack combinations\n- Built-in best practices for security, performance, and scalability`,
      category: 'CODING',
      tier: 'S',
      domain: 'coding',
      tags: JSON.stringify(['fullstack', 'scaffolding', 'generator', 'project-setup', 'api', 'database', 'frontend', 'devops']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      price: 12.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'FILE_SYSTEM', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 5670,
      rating: 4.8,
      reviewCount: 89,
    },

    // ?�?�?� TIER A  (Premium Mid) ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
    {
      name: 'Phantom Designer',
      slug: 'phantom-designer',
      description: 'Autonomous UI/UX design agent that operates Figma, creates design systems, generates responsive mockups, and exports production-ready assets.',
      longDescription: `Phantom Designer is an AI design partner that controls Figma and other design tools natively. It doesn't generate static images ??it creates real, editable design files with proper layers, components, and auto-layout.\n\n**Design Capabilities:**\n- Complete UI design from wireframe to high-fidelity\n- Design system generation (colors, typography, spacing, components)\n- Responsive layout creation for mobile, tablet, desktop\n- Icon and illustration generation\n- Prototype creation with interactions and animations\n- Asset export (SVG, PNG, PDF) in multiple resolutions\n- Dark/light theme variant generation\n\n**Supported Tools:**\n- Figma (primary)\n- Adobe XD, Sketch (via mouse/keyboard control)\n- GIMP, Photoshop for image editing tasks\n\n**Performance:**\n- Creates a full landing page design in ~8 minutes\n- Generates 50+ component design systems\n- Color palette generation with WCAG accessibility compliance`,
      category: 'DESIGN',
      tier: 'A',
      domain: 'design',
      tags: JSON.stringify(['design', 'figma', 'ui-ux', 'mockup', 'design-system', 'responsive', 'prototyping']),
      capabilities: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'WINDOW_MANAGEMENT', 'FILE_SYSTEM']),
      price: 9.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 4230,
      rating: 4.7,
      reviewCount: 64,
    },
    {
      name: 'DataForge',
      slug: 'dataforge',
      description: 'Advanced data analysis agent ??processes datasets up to 10M rows, creates visualizations, statistical models, and executive-ready reports.',
      longDescription: `DataForge is a data scientist in agent form. It operates Excel, Python (Jupyter/pandas), R, and BI tools to deliver complete analytical workflows.\n\n**Analysis Pipeline:**\n1. **Data Ingestion** ??CSV, Excel, JSON, Parquet, SQL databases\n2. **Cleaning & Prep** ??missing values, outliers, type casting, normalization\n3. **Exploratory Analysis** ??distributions, correlations, trends, anomalies\n4. **Visualization** ??charts, heatmaps, dashboards (matplotlib, plotly, seaborn)\n5. **Modeling** ??regression, classification, clustering, time series\n6. **Reporting** ??PDF/HTML reports with executive summaries\n\n**Performance Benchmarks:**\n- Processes 10M row CSVs in under 2 minutes\n- Generates 20+ chart types automatically\n- Statistical significance testing built-in\n- Supports A/B test analysis, cohort analysis, funnel analysis\n\n**Output Formats:**\n- Interactive HTML dashboards\n- PDF executive reports\n- Excel workbooks with pivot tables\n- Python notebooks (reproducible analysis)`,
      category: 'DATA_ANALYSIS',
      tier: 'A',
      domain: 'data_analysis',
      tags: JSON.stringify(['data', 'analysis', 'visualization', 'statistics', 'excel', 'python', 'reporting', 'machine-learning']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      price: 9.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 3890,
      rating: 4.8,
      reviewCount: 56,
    },
    {
      name: 'Recon',
      slug: 'recon',
      description: 'Deep web research agent with source verification, multi-tab browsing, structured data extraction, and automated report generation.',
      longDescription: `Recon is a research powerhouse. It opens Chrome, navigates the web autonomously, reads pages, cross-references sources, and compiles structured research reports ??all without manual intervention.\n\n**Research Capabilities:**\n- Multi-tab parallel browsing for faster research\n- Academic paper search (Google Scholar, arXiv, PubMed)\n- News aggregation with source credibility scoring\n- Competitive analysis with structured comparison tables\n- Patent and trademark searches\n- Social media trend analysis\n- Data extraction from tables, charts, and documents\n\n**Report Formats:**\n- Structured Markdown reports with citations\n- Executive summaries with key findings\n- SWOT analysis templates\n- Comparison matrices\n- Source credibility ratings\n\n**Anti-Hallucination:**\n- Every claim is linked to a verifiable source URL\n- Confidence scores on each finding\n- Contradicting source detection\n\n**Performance:**\n- Researches 50+ sources per query\n- Average research time: 5-15 minutes\n- 97.3% source accuracy rate`,
      category: 'RESEARCH',
      tier: 'A',
      domain: 'research',
      tags: JSON.stringify(['research', 'web-scraping', 'analysis', 'browser', 'reports', 'academic', 'competitive-analysis']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 6740,
      rating: 4.6,
      reviewCount: 93,
    },

    // ?�?�?� TIER B  (Mid-Range) ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
    {
      name: 'Scribe',
      slug: 'scribe',
      description: 'Professional content writing agent ??blog posts, documentation, emails, marketing copy, with SEO optimization and tone control.',
      longDescription: `Scribe is a professional-grade writing assistant that operates directly in your text editor, CMS, or browser. It doesn't just generate text ??it writes, edits, formats, and publishes complete content.\n\n**Content Types:**\n- Long-form blog posts (2000-5000 words)\n- Technical documentation with code samples\n- Marketing copy (landing pages, ads, emails)\n- Social media content calendars\n- Newsletter campaigns\n- Product descriptions\n- Press releases and announcements\n\n**SEO Features:**\n- Keyword research and density optimization\n- Meta title and description generation\n- Internal linking suggestions\n- Readability score optimization (Flesch-Kincaid)\n- Header structure optimization (H1-H6)\n\n**Tone Profiles:**\n- Professional / Corporate\n- Casual / Conversational\n- Technical / Academic\n- Persuasive / Marketing\n- Custom tone via example text\n\n**Output:**\n- Writes directly in Google Docs, Notion, Word, or any editor\n- Formats with headers, lists, bold, italics\n- Inserts images and media placeholders`,
      category: 'WRITING',
      tier: 'B',
      domain: 'writing',
      tags: JSON.stringify(['writing', 'content', 'seo', 'blog', 'marketing', 'documentation', 'copywriting']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 5120,
      rating: 4.5,
      reviewCount: 78,
    },
    {
      name: 'Taskmaster',
      slug: 'taskmaster',
      description: 'OS automation agent ??batch file operations, software installation, system configuration, scheduled tasks, and cross-app workflow automation.',
      longDescription: `Taskmaster automates everything you do manually on your computer. File management, software setup, system tweaks, and multi-app workflows ??describe it once, and Taskmaster handles it forever.\n\n**Automation Categories:**\n\n**File Management**\n- Batch rename with regex patterns\n- Intelligent file organization by type/date/project\n- Duplicate detection and cleanup\n- Automated backup to local/cloud storage\n\n**Software Management**\n- Unattended software installation (chocolatey, winget, brew)\n- Development environment setup (Node, Python, Docker, etc.)\n- Configuration migration between machines\n\n**System Configuration**\n- Registry/plist modifications\n- Environment variable management\n- Firewall and network configuration\n- Scheduled task creation\n\n**Cross-App Workflows**\n- Data transfer between applications\n- Report generation from multiple sources\n- Email attachment processing\n- Screenshot-based app automation\n\n**Safety:**\n- Sandbox mode for testing before execution\n- Undo/rollback support for file operations\n- Confirmation prompts for destructive actions`,
      category: 'AUTOMATION',
      tier: 'B',
      domain: 'automation',
      tags: JSON.stringify(['automation', 'system', 'files', 'workflow', 'batch', 'devops', 'setup']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'WINDOW_MANAGEMENT', 'APP_MANAGEMENT', 'SCREEN_CAPTURE']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'WINDOW_MANAGEMENT']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 4560,
      rating: 4.7,
      reviewCount: 71,
    },
    {
      name: 'PixelSmith',
      slug: 'pixelsmith',
      description: 'Image editing and batch processing agent ??photo retouching, background removal, format conversion, watermarking, and social media asset generation.',
      longDescription: `PixelSmith operates image editing software (Photoshop, GIMP, Paint.NET) to perform professional image editing tasks at scale.\n\n**Editing Capabilities:**\n- Photo retouching and enhancement\n- Background removal and replacement\n- Color correction and grading\n- Object removal and inpainting\n- Text overlay and watermarking\n- Resize and crop for multiple platforms\n\n**Batch Processing:**\n- Process hundreds of images with consistent settings\n- Social media asset generation (Instagram, Twitter, LinkedIn, YouTube)\n- E-commerce product photo optimization\n- Thumbnail generation at multiple sizes\n- Format conversion (PNG, JPEG, WebP, SVG, AVIF)\n\n**Templates:**\n- Social media post templates\n- Banner and header templates\n- Product showcase templates\n- Before/after comparison layouts\n\n**Performance:**\n- Processes 100 images in ~5 minutes\n- Supports images up to 8K resolution\n- Non-destructive editing with layer support`,
      category: 'DESIGN',
      tier: 'B',
      domain: 'design',
      tags: JSON.stringify(['image-editing', 'batch-processing', 'photos', 'graphics', 'social-media', 'photoshop']),
      capabilities: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 5.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 3210,
      rating: 4.6,
      reviewCount: 45,
    },

    // ?�?�?� TIER C  (Affordable / Free) ?�?�?�?�?�?�?�?�?�
    {
      name: 'Codewatch',
      slug: 'codewatch',
      description: 'Automated code review agent ??scans repos for bugs, security vulnerabilities, performance issues, and style violations with detailed fix suggestions.',
      longDescription: `Codewatch is a focused code review agent. Point it at any codebase and it will perform a comprehensive audit covering security, performance, correctness, and code quality.\n\n**Review Categories:**\n\n**Security**\n- SQL injection, XSS, CSRF detection\n- Hardcoded secrets and API keys\n- Insecure dependencies (CVE checking)\n- Authentication and authorization flaws\n\n**Performance**\n- N+1 query detection\n- Memory leak patterns\n- Unnecessary re-renders (React)\n- Algorithmic complexity warnings\n\n**Correctness**\n- Null/undefined handling\n- Race conditions\n- Off-by-one errors\n- Type mismatches\n\n**Code Quality**\n- Dead code detection\n- Copy-paste duplication\n- Function complexity (cyclomatic)\n- Naming convention violations\n\n**Output:**\n- Inline comments on problem lines\n- Severity ratings (Critical to Info)\n- Auto-fix PRs for simple issues\n- Summary report with prioritized action items`,
      category: 'CODING',
      tier: 'C',
      domain: 'coding',
      tags: JSON.stringify(['code-review', 'security', 'bugs', 'linting', 'audit', 'quality']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS', 'CLIPBOARD']),
      price: 3.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'SYSTEM_COMMANDS']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 7890,
      rating: 4.5,
      reviewCount: 112,
    },
    {
      name: 'Deployer',
      slug: 'deployer',
      description: 'One-click deployment agent ??Dockerizes apps, configures cloud infrastructure (AWS/GCP/Vercel), sets up domains, SSL, and monitoring.',
      longDescription: `Deployer takes your local project and puts it live on the internet. It handles containerization, cloud configuration, domain setup, and monitoring ??turning "it works on my machine" into "it works in production."\n\n**Deployment Targets:**\n- AWS (EC2, ECS, Lambda, S3 + CloudFront)\n- Google Cloud (Cloud Run, GKE, App Engine)\n- Vercel / Netlify (static + serverless)\n- DigitalOcean (Droplets, App Platform)\n- Self-hosted (Docker Compose + Nginx)\n\n**What Deployer Does:**\n1. Analyzes your project structure and tech stack\n2. Generates optimized Dockerfile and docker-compose.yml\n3. Creates cloud infrastructure configs (Terraform/CloudFormation)\n4. Sets up CI/CD pipeline (GitHub Actions / GitLab CI)\n5. Configures custom domain + SSL certificates\n6. Sets up monitoring and alerting (health checks, logs)\n7. Performs zero-downtime deployment\n\n**Supported Stacks:**\n- Node.js / Next.js / React / Vue\n- Python / Django / FastAPI / Flask\n- Go / Rust / Java / .NET\n- Static sites and SPAs`,
      category: 'AUTOMATION',
      tier: 'A',
      domain: 'automation',
      tags: JSON.stringify(['deployment', 'devops', 'docker', 'aws', 'cloud', 'ci-cd', 'infrastructure']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 2980,
      rating: 4.7,
      reviewCount: 38,
    },
    {
      name: 'Scrappy',
      slug: 'scrappy',
      description: 'Web scraping and data extraction agent ??scrapes websites, APIs, fills forms, downloads files, and structures data into CSV/JSON/Excel.',
      longDescription: `Scrappy is a lightweight but powerful data extraction agent. It navigates websites, handles pagination, fills forms, bypasses CAPTCHAs (where legally permitted), and structures the extracted data.\n\n**Extraction Modes:**\n\n**Web Scraping**\n- Product listings from e-commerce sites\n- Job postings from career portals\n- Real estate listings\n- News articles and blog posts\n- Social media profiles (public data)\n\n**Form Automation**\n- Auto-fill web forms from spreadsheet data\n- Batch submission with error handling\n- File upload automation\n\n**Data Structuring**\n- Automatic table detection and extraction\n- JSON/CSV/Excel output with custom schemas\n- Data deduplication and cleaning\n- Image and file downloading\n\n**Smart Features:**\n- Handles infinite scroll and lazy loading\n- Pagination auto-detection\n- Rate limiting to respect robots.txt\n- Session/cookie management\n- Retry logic for failed requests\n\n**Output Formats:**\n- CSV, JSON, Excel, SQLite, Google Sheets`,
      category: 'DATA_ANALYSIS',
      tier: 'C',
      domain: 'data_analysis',
      tags: JSON.stringify(['scraping', 'data-extraction', 'web', 'automation', 'csv', 'forms']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 9120,
      rating: 4.4,
      reviewCount: 134,
    },
    {
      name: 'Quill',
      slug: 'quill',
      description: 'Free open-source note-taking and knowledge organization agent ??captures, tags, links, and structures your research across Obsidian, Notion, and markdown files.',
      longDescription: `Quill is a free, community-built knowledge management agent. It helps you capture, organize, and connect your ideas and research across your favorite note-taking apps.\n\n**Supported Apps:**\n- Obsidian (native vault support)\n- Notion (via browser automation)\n- Markdown files (any editor)\n- Google Docs\n\n**Features:**\n\n**Smart Capture**\n- Web page to structured notes with metadata\n- Screenshot to OCR to searchable note\n- YouTube video to timestamped summary\n- PDF to highlighted key points\n\n**Auto-Organization**\n- Automatic tagging based on content analysis\n- Bidirectional link suggestion\n- Topic clustering and mind map generation\n- Daily note compilation\n\n**Knowledge Graph**\n- Visual connection mapping between notes\n- Related content suggestions\n- Spaced repetition integration for learning\n- Quick search across all notes\n\n**Philosophy:**\nQuill is free and open-source because knowledge organization should be accessible to everyone. Built by the community, for the community.`,
      category: 'PRODUCTIVITY',
      tier: 'F',
      domain: 'productivity',
      tags: JSON.stringify(['notes', 'obsidian', 'notion', 'knowledge', 'organization', 'free', 'open-source']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD', 'BROWSER_CONTROL']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 12400,
      rating: 4.6,
      reviewCount: 186,
    },

    // =====================================================
    //  TIER B-  (Budget $3-7)
    // =====================================================
    {
      name: 'QuickType',
      slug: 'quicktype',
      description: 'Simple keyboard macro agent. Records and replays typing sequences, fills forms, and expands text snippets across any application.',
      longDescription: `QuickType is a lightweight typing automation agent. Record a sequence of keystrokes and replay them on demand.\n\n**Features:**\n- Text snippet expansion (shortcuts to long text)\n- Form auto-fill from templates\n- Repeated typing tasks on schedule\n- Basic find-and-replace across open documents\n\nSimple, cheap, effective.`,
      category: 'AUTOMATION',
      tier: 'B-',
      domain: 'automation',
      tags: JSON.stringify(['typing', 'macro', 'forms', 'automation', 'budget']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      price: 0.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 18900,
      rating: 4.0,
      reviewCount: 245,
    },
    {
      name: 'ScreenSnap',
      slug: 'screensnap',
      description: 'Budget screenshot and screen recording agent. Captures screens, annotates with arrows/text, and saves to common formats.',
      longDescription: `ScreenSnap captures your screen and adds basic annotations.\n\n**Features:**\n- Full screen or region capture\n- Basic annotation: arrows, rectangles, text labels\n- Auto-save to PNG/JPEG with timestamps\n- Simple screen recording to GIF\n\nNo frills, just works.`,
      category: 'PRODUCTIVITY',
      tier: 'B-',
      domain: 'productivity',
      tags: JSON.stringify(['screenshot', 'recording', 'annotation', 'budget']),
      capabilities: JSON.stringify(['SCREEN_CAPTURE', 'FILE_SYSTEM']),
      price: 0.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 22100,
      rating: 3.9,
      reviewCount: 312,
    },
    {
      name: 'FileSorter',
      slug: 'filesorter',
      description: 'Automatic file organization agent. Sorts downloads folder, renames files by pattern, and moves files into categorized directories.',
      longDescription: `FileSorter keeps your filesystem clean.\n\n**Features:**\n- Auto-sort Downloads folder by file type\n- Bulk rename with date/counter patterns\n- Duplicate file finder and remover\n- Scheduled cleanup runs\n\nSet it and forget it.`,
      category: 'AUTOMATION',
      tier: 'B-',
      domain: 'automation',
      tags: JSON.stringify(['files', 'organization', 'cleanup', 'automation', 'budget']),
      capabilities: JSON.stringify(['FILE_SYSTEM']),
      price: 1.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 1980,
      rating: 4.9,
      reviewCount: 87,
    },

    // =====================================================
    //  TIER B-  (Budget $0.99-$1.99)
    // =====================================================
    {
      name: 'Clippy',
      slug: 'clippy',
      description: 'Clipboard manager agent. Saves clipboard history, supports pinned items, and pastes from history on demand.',
      longDescription: `Clippy manages your clipboard history.\n\n**Features:**\n- Stores last 100 clipboard entries\n- Pin important items for quick access\n- Search clipboard history by keyword\n- Paste any previous item with hotkey\n\nNever lose a copied item again.`,
      category: 'PRODUCTIVITY',
      tier: 'B-',
      domain: 'productivity',
      tags: JSON.stringify(['clipboard', 'history', 'paste', 'budget', 'utility']),
      capabilities: JSON.stringify(['CLIPBOARD', 'KEYBOARD_INPUT']),
      price: 0.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['CLIPBOARD', 'KEYBOARD_INPUT']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 19200,
      rating: 4.1,
      reviewCount: 267,
    },
    {
      name: 'BashBuddy',
      slug: 'bashbuddy',
      description: 'Simple terminal command assistant. Translates natural language to shell commands, explains errors, and suggests fixes.',
      longDescription: `BashBuddy helps you with terminal commands.\n\n**Features:**\n- Natural language to bash/PowerShell commands\n- Explains what a command does before running it\n- Parses error output and suggests fixes\n- Common command cheat sheet\n- Perfect for terminal beginners.`,
      category: 'CODING',
      tier: 'B-',
      domain: 'coding',
      tags: JSON.stringify(['terminal', 'bash', 'commands', 'beginner', 'budget']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'KEYBOARD_INPUT']),
      price: 1.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'KEYBOARD_INPUT']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 14300,
      rating: 4.3,
      reviewCount: 189,
    },
    {
      name: 'WebWatch',
      slug: 'webwatch',
      description: 'Website monitoring agent. Checks if websites are up, detects content changes, and sends desktop notifications.',
      longDescription: `WebWatch monitors websites for you.\n\n**Features:**\n- Periodic uptime checks (1-60 min intervals)\n- Content change detection with diff highlighting\n- Desktop notifications on changes\n- Simple availability reports\n- Ideal for tracking price drops, stock availability, or site outages.`,
      category: 'AUTOMATION',
      tier: 'B-',
      domain: 'automation',
      tags: JSON.stringify(['monitoring', 'websites', 'notifications', 'tracking', 'budget']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'SCREEN_CAPTURE']),
      price: 1.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 11800,
      rating: 4.1,
      reviewCount: 156,
    },

    // =====================================================
    //  TIER F  (Free)
    // =====================================================
    {
      name: 'ClickBot',
      slug: 'clickbot',
      description: 'Free auto-clicker agent. Clicks at specified coordinates on a timer. Simple but useful for repetitive clicking tasks.',
      longDescription: `ClickBot clicks stuff for you.\n\n**Features:**\n- Click at (x, y) coordinates on interval\n- Configurable click speed (100ms - 10s)\n- Left/right/double click modes\n- Start/stop with hotkey\n\nThe simplest agent on the platform. Free forever.`,
      category: 'AUTOMATION',
      tier: 'F',
      domain: 'automation',
      tags: JSON.stringify(['clicker', 'automation', 'free', 'simple', 'mouse']),
      capabilities: JSON.stringify(['MOUSE_CONTROL']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['MOUSE_CONTROL']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 34200,
      rating: 3.8,
      reviewCount: 420,
    },
    {
      name: 'NoteGrab',
      slug: 'notegrab',
      description: 'Free clipboard-to-file saver. Copies text from clipboard and appends it to a running notes file. Zero configuration.',
      longDescription: `NoteGrab saves your clipboard to a file.\n\n**Features:**\n- Watch clipboard for new text\n- Append to daily notes file with timestamp\n- Plain text, zero formatting\n- Works in background\n\nThe simplest note-taking workflow. Press Ctrl+C anywhere, find it in notes.txt later.`,
      category: 'PRODUCTIVITY',
      tier: 'F',
      domain: 'productivity',
      tags: JSON.stringify(['notes', 'clipboard', 'free', 'simple', 'text']),
      capabilities: JSON.stringify(['CLIPBOARD', 'FILE_SYSTEM']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['CLIPBOARD', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 28700,
      rating: 4.0,
      reviewCount: 356,
    },
    {
      name: 'Timer',
      slug: 'timer',
      description: 'Free Pomodoro timer agent. Shows focus/break notifications on screen. Tracks daily work sessions in a log file.',
      longDescription: `Timer keeps you focused with the Pomodoro technique.\n\n**Features:**\n- 25-min focus / 5-min break cycles\n- Desktop notification on cycle end\n- Daily session log (plain text)\n- Customizable cycle lengths\n\nSimple time management. Free.`,
      category: 'PRODUCTIVITY',
      tier: 'F',
      domain: 'productivity',
      tags: JSON.stringify(['timer', 'pomodoro', 'focus', 'free', 'simple']),
      capabilities: JSON.stringify(['SCREEN_CAPTURE', 'FILE_SYSTEM']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 25100,
      rating: 4.2,
      reviewCount: 298,
    },
    {
      name: 'SysMon Lite',
      slug: 'sysmon-lite',
      description: 'Free system monitor agent. Shows CPU, RAM, and disk usage in a simple overlay. Logs stats to CSV.',
      longDescription: `SysMon Lite monitors your system resources.\n\n**Features:**\n- Real-time CPU, RAM, disk usage\n- Logs to CSV for later analysis\n- Process list with memory usage\n- Simple text-based output\n\nLightweight system monitoring. Zero cost.`,
      category: 'AUTOMATION',
      tier: 'F',
      domain: 'automation',
      tags: JSON.stringify(['system', 'monitoring', 'cpu', 'ram', 'free', 'lightweight']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 21500,
      rating: 4.0,
      reviewCount: 278,
    },
    {
      name: 'LinkCheck',
      slug: 'linkcheck',
      description: 'Free broken link checker. Crawls a URL and reports all broken links. Simple HTML report output.',
      longDescription: `LinkCheck finds broken links on websites.\n\n**Features:**\n- Crawls pages from a starting URL\n- Reports 404s and timeout errors\n- Simple HTML output report\n- Configurable crawl depth (1-3 levels)\n\nKeep your website link-rot free. Free to use.`,
      category: 'AUTOMATION',
      tier: 'F',
      domain: 'automation',
      tags: JSON.stringify(['links', 'checker', 'website', 'seo', 'free']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'FILE_SYSTEM']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 16400,
      rating: 3.9,
      reviewCount: 201,
    },
    {
      name: 'HashCalc',
      slug: 'hashcalc',
      description: 'Free file hash calculator. Computes MD5, SHA-1, SHA-256 hashes for files and verifies integrity. Command-line simple.',
      longDescription: `HashCalc computes file hashes.\n\n**Features:**\n- MD5, SHA-1, SHA-256 hash computation\n- Compare hash against expected value\n- Batch hash multiple files\n- Output to text file\n\nVerify file integrity. Free and open source.`,
      category: 'AUTOMATION',
      tier: 'F',
      domain: 'automation',
      tags: JSON.stringify(['hash', 'checksum', 'security', 'files', 'free']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 13200,
      rating: 4.1,
      reviewCount: 167,
    },

    // ═══════════════════════════════════════════════════
    //  NEW AGENTS — 37 agents across all 12 categories
    // ═══════════════════════════════════════════════════

    // ─── COMMUNICATION (5) ───────────────────────────

    {
      name: 'Nexus Chat',
      slug: 'nexus-chat',
      description: 'Multi-platform communication manager — compose emails, Slack/Discord/Teams messages, schedule meetings, and manage professional correspondence across all platforms.',
      longDescription: `Nexus Chat is your unified communication command center. It operates email clients, Slack, Discord, Teams, and calendar apps to handle all your professional communication.\n\n**Capabilities:**\n- Email composition with tone adaptation\n- Slack/Discord channel messaging\n- Teams meeting scheduling\n- Multi-thread summarization\n- Priority classification\n- Template-based responses\n- Follow-up automation\n\n**Tone Profiles:**\n- Executive / Board-level\n- Team / Casual professional\n- Client / External\n- Urgent / Crisis\n\n**Performance:**\n- Composes emails 5x faster than manual\n- Handles 50+ messages per session\n- Meeting scheduling with conflict detection`,
      category: 'COMMUNICATION',
      tier: 'S',
      domain: 'communication',
      tags: JSON.stringify(['communication', 'email', 'slack', 'discord', 'teams', 'meetings', 'messaging']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 3420,
      rating: 4.7,
      reviewCount: 52,
    },
    {
      name: 'MailForge',
      slug: 'mailforge',
      description: 'Professional email composition and management agent — write, format, and send emails with perfect tone, structure, and follow-up tracking.',
      longDescription: `MailForge specializes in email. From cold outreach to executive briefs, it crafts emails that get responses.\n\n**Features:**\n- Professional email templates (inquiry, follow-up, proposal, apology)\n- Tone calibration (formal, friendly, urgent, diplomatic)\n- Subject line optimization (A/B variants)\n- Follow-up sequence generation\n- Bulk email personalization\n\n**Use Cases:**\n- Sales outreach campaigns\n- Client status updates\n- Internal team announcements\n- Job application emails\n- Customer support responses`,
      category: 'COMMUNICATION',
      tier: 'A',
      domain: 'communication',
      tags: JSON.stringify(['email', 'communication', 'professional', 'templates', 'outreach']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 2890,
      rating: 4.6,
      reviewCount: 38,
    },
    {
      name: 'MeetBot',
      slug: 'meetbot',
      description: 'Meeting scheduler and notes agent — create calendar events, write agendas, take meeting notes, and send follow-up action items.',
      longDescription: `MeetBot handles all meeting logistics. Schedule, prepare agendas, take notes, and distribute action items.\n\n**Features:**\n- Calendar event creation (Google Calendar, Outlook)\n- Agenda templates by meeting type\n- Meeting notes with action item extraction\n- Follow-up email generation\n- Recurring meeting management\n\n**Meeting Types:**\n- 1:1s, standups, retrospectives, planning, reviews, all-hands`,
      category: 'COMMUNICATION',
      tier: 'B',
      domain: 'communication',
      tags: JSON.stringify(['meetings', 'calendar', 'scheduling', 'notes', 'agenda']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 4120,
      rating: 4.5,
      reviewCount: 61,
    },
    {
      name: 'SlackOps',
      slug: 'slackops',
      description: 'Slack/Discord/Teams message automation — post formatted messages, manage channels, automate announcements, and monitor conversations.',
      longDescription: `SlackOps automates your team messaging workflow.\n\n**Features:**\n- Channel message posting with rich formatting\n- Automated status updates and announcements\n- Thread summarization\n- @mention management\n- Cross-platform message formatting (Slack, Discord, Teams)\n\n**Automation:**\n- Scheduled daily/weekly messages\n- Template-based responses\n- Channel topic updates`,
      category: 'COMMUNICATION',
      tier: 'C',
      domain: 'communication',
      tags: JSON.stringify(['slack', 'discord', 'teams', 'messaging', 'automation']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL', 'CLIPBOARD']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'BROWSER_CONTROL']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 5670,
      rating: 4.3,
      reviewCount: 74,
    },
    {
      name: 'QuickReply',
      slug: 'quickreply',
      description: 'Fast message template and reply agent — instant professional responses with customizable templates for email, chat, and social media.',
      longDescription: `QuickReply generates fast, professional responses.\n\n**Features:**\n- Pre-built reply templates (acknowledge, decline, confirm, defer)\n- Tone matching to original message\n- Multi-platform formatting\n- Quick response generation under 30 seconds\n\nPerfect for busy professionals who need fast, polished replies.`,
      category: 'COMMUNICATION',
      tier: 'B-',
      domain: 'communication',
      tags: JSON.stringify(['reply', 'templates', 'quick', 'messaging', 'budget']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      price: 1.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 8340,
      rating: 4.2,
      reviewCount: 112,
    },

    // ─── MEDIA (5) ───────────────────────────────────

    {
      name: 'MediaForge',
      slug: 'mediaforge',
      description: 'Professional video/audio production agent — edit videos, process audio, add subtitles, create thumbnails, and convert formats using ffmpeg.',
      longDescription: `MediaForge is a complete multimedia production toolkit. It uses ffmpeg and desktop tools to handle any video or audio task.\n\n**Video Capabilities:**\n- Trim, cut, merge video clips\n- Resize and transcode (H.264, H.265, VP9)\n- Add subtitles (SRT, ASS)\n- Watermark overlay\n- Speed adjustment\n- Frame extraction\n\n**Audio Capabilities:**\n- Format conversion (MP3, WAV, AAC, FLAC, OGG)\n- Volume normalization\n- Audio mixing and merging\n- Noise reduction\n- Podcast editing\n\n**Performance:**\n- Processes 1080p video at 2x realtime\n- Batch processing for multiple files\n- Quality-optimized encoding settings`,
      category: 'MEDIA',
      tier: 'S',
      domain: 'media',
      tags: JSON.stringify(['video', 'audio', 'ffmpeg', 'editing', 'production', 'subtitles', 'encoding']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'MOUSE_CONTROL', 'CLIPBOARD']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 2780,
      rating: 4.7,
      reviewCount: 41,
    },
    {
      name: 'AudioCraft',
      slug: 'audiocraft',
      description: 'Audio processing and podcast editing agent — convert formats, normalize volume, trim clips, mix tracks, and edit podcast episodes.',
      longDescription: `AudioCraft handles all audio processing tasks using ffmpeg and audio tools.\n\n**Features:**\n- Format conversion (MP3, WAV, AAC, FLAC, OGG)\n- Volume normalization and loudness targeting\n- Audio trimming and splitting\n- Multi-track mixing\n- Podcast episode editing\n- Metadata tagging\n\n**Quality Settings:**\n- Lossless: FLAC, WAV\n- High quality: MP3 320kbps, AAC 256kbps\n- Podcast standard: MP3 128kbps mono`,
      category: 'MEDIA',
      tier: 'A',
      domain: 'media',
      tags: JSON.stringify(['audio', 'podcast', 'editing', 'conversion', 'ffmpeg', 'mixing']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 8.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 1980,
      rating: 4.6,
      reviewCount: 29,
    },
    {
      name: 'VideoClip',
      slug: 'videoclip',
      description: 'Video trimming and format conversion agent — cut clips, change resolution, convert between formats, and merge video segments.',
      longDescription: `VideoClip handles everyday video editing tasks.\n\n**Features:**\n- Video trimming with precise timestamps\n- Format conversion (MP4, AVI, MKV, WebM, MOV)\n- Resolution scaling (4K → 1080p → 720p → 480p)\n- Video merging/concatenation\n- Frame rate adjustment\n- Basic speed control\n\nSimple, reliable video processing.`,
      category: 'MEDIA',
      tier: 'B',
      domain: 'media',
      tags: JSON.stringify(['video', 'trimming', 'conversion', 'editing', 'format']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 5.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 3450,
      rating: 4.4,
      reviewCount: 48,
    },
    {
      name: 'ThumbnailGen',
      slug: 'thumbnailgen',
      description: 'Thumbnail and social media graphics generator — extract video frames, create YouTube thumbnails, and generate platform-optimized images.',
      longDescription: `ThumbnailGen creates thumbnails and social media graphics.\n\n**Features:**\n- Video frame extraction at best timestamp\n- YouTube thumbnail (1280x720)\n- Instagram post (1080x1080)\n- Twitter header (1500x500)\n- Facebook cover (820x312)\n- Custom dimensions\n- Text overlay on images\n\nOptimized for all major platforms.`,
      category: 'MEDIA',
      tier: 'C',
      domain: 'media',
      tags: JSON.stringify(['thumbnail', 'social-media', 'graphics', 'youtube', 'instagram']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'SCREEN_CAPTURE', 'KEYBOARD_INPUT']),
      price: 3.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 6780,
      rating: 4.3,
      reviewCount: 89,
    },
    {
      name: 'GifMaker',
      slug: 'gifmaker',
      description: 'Free video-to-GIF converter — create optimized GIFs from video clips with palette optimization and size control.',
      longDescription: `GifMaker converts video clips to GIFs.\n\n**Features:**\n- Video to GIF conversion\n- Palette optimization for quality\n- Frame rate control\n- Size/resolution scaling\n- Duration trimming\n\nKeep your GIFs under 10MB with automatic optimization. Free forever.`,
      category: 'MEDIA',
      tier: 'F',
      domain: 'media',
      tags: JSON.stringify(['gif', 'video', 'conversion', 'free', 'animation']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 15200,
      rating: 4.1,
      reviewCount: 198,
    },

    // ─── MONITORING (5) ──────────────────────────────

    {
      name: 'Sentinel Watch',
      slug: 'sentinel-watch',
      description: 'Enterprise monitoring agent — check system health, analyze logs, track performance metrics, detect anomalies, and generate monitoring reports.',
      longDescription: `Sentinel Watch is your enterprise-grade monitoring solution.\n\n**Monitoring Capabilities:**\n- System health (CPU, RAM, disk, network)\n- Windows Event Log analysis\n- Service status monitoring\n- Performance counter tracking\n- Anomaly detection with threshold alerts\n- Network connectivity checks\n\n**Reports:**\n- Real-time dashboard-style output\n- Historical trend analysis\n- Incident detection and alerting\n- Executive health summaries\n\n**Performance:**\n- 50+ metrics per scan\n- Event log analysis: 1000 entries in seconds\n- Continuous monitoring with configurable intervals`,
      category: 'MONITORING',
      tier: 'S',
      domain: 'monitoring',
      tags: JSON.stringify(['monitoring', 'system-health', 'logs', 'alerts', 'performance', 'enterprise']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 1890,
      rating: 4.8,
      reviewCount: 27,
    },
    {
      name: 'LogHound',
      slug: 'loghound',
      description: 'Log analysis and anomaly detection agent — parse Windows Event Logs, filter by severity, detect patterns, and create analysis reports.',
      longDescription: `LogHound specializes in log file analysis.\n\n**Features:**\n- Windows Event Log parsing (System, Application, Security)\n- Severity filtering (Error, Warning, Critical)\n- Pattern detection across log entries\n- Anomaly identification\n- Time-based correlation\n- Structured analysis reports\n\n**Output:**\n- Error frequency charts\n- Top issues by occurrence\n- Timeline visualization\n- Recommended actions`,
      category: 'MONITORING',
      tier: 'A',
      domain: 'monitoring',
      tags: JSON.stringify(['logs', 'analysis', 'monitoring', 'anomaly', 'event-log', 'patterns']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 2340,
      rating: 4.5,
      reviewCount: 33,
    },
    {
      name: 'UptimeGuard',
      slug: 'uptimeguard',
      description: 'Website and service uptime monitoring — HTTP health checks, ping tests, port checks, SSL certificate expiry, and availability reporting.',
      longDescription: `UptimeGuard monitors your websites and services.\n\n**Checks:**\n- HTTP status codes and response times\n- ICMP ping and packet loss\n- TCP port availability\n- DNS resolution\n- SSL certificate expiry dates\n\n**Reporting:**\n- Uptime percentage calculation\n- Response time tracking\n- Downtime incident logging\n- Simple HTML/text reports`,
      category: 'MONITORING',
      tier: 'B',
      domain: 'monitoring',
      tags: JSON.stringify(['uptime', 'monitoring', 'health-check', 'availability', 'ssl', 'http']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'BROWSER_CONTROL']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 4560,
      rating: 4.4,
      reviewCount: 58,
    },
    {
      name: 'PerfTracker',
      slug: 'perftracker',
      description: 'Performance metrics tracking agent — monitor CPU, RAM, disk I/O, and network throughput with periodic sampling and CSV export.',
      longDescription: `PerfTracker collects and reports system performance metrics.\n\n**Metrics:**\n- CPU usage (per-core and total)\n- RAM utilization and availability\n- Disk I/O (read/write speeds)\n- Network throughput\n- Process-level resource consumption\n\n**Output:**\n- CSV data export for charting\n- Summary statistics (avg, max, min)\n- Threshold breach alerts\n- Simple text reports`,
      category: 'MONITORING',
      tier: 'C',
      domain: 'monitoring',
      tags: JSON.stringify(['performance', 'metrics', 'cpu', 'ram', 'monitoring', 'tracking']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'SCREEN_CAPTURE']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 5890,
      rating: 4.2,
      reviewCount: 76,
    },
    {
      name: 'PingBot',
      slug: 'pingbot',
      description: 'Free simple ping and port check agent — test connectivity to hosts, check open ports, and measure latency.',
      longDescription: `PingBot checks if things are reachable.\n\n**Features:**\n- ICMP ping with latency measurement\n- TCP port checking\n- Packet loss reporting\n- Basic traceroute\n\nThe simplest network monitoring tool. Free.`,
      category: 'MONITORING',
      tier: 'F',
      domain: 'monitoring',
      tags: JSON.stringify(['ping', 'network', 'monitoring', 'free', 'connectivity']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 19800,
      rating: 4.0,
      reviewCount: 245,
    },

    // ─── SYSTEM (5) ──────────────────────────────────

    {
      name: 'SysForge',
      slug: 'sysforge',
      description: 'Full system administration agent — manage Windows services, network configuration, disk, processes, registry, scheduled tasks, and OS optimization.',
      longDescription: `SysForge is a comprehensive system administration agent.\n\n**System Management:**\n- Service management (start, stop, restart, configure)\n- Network configuration (IP, DNS, firewall rules)\n- Disk management (space analysis, cleanup, health)\n- Process management (list, kill, priority)\n- Registry operations (read, backup)\n- Scheduled task management\n- Environment variable configuration\n- System optimization\n\n**Safety:**\n- Automatic backup before modifications\n- Rollback support for critical changes\n- Confirmation prompts for destructive operations\n- Audit trail logging`,
      category: 'SYSTEM',
      tier: 'S',
      domain: 'system',
      tags: JSON.stringify(['system', 'admin', 'services', 'network', 'disk', 'registry', 'enterprise']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'WINDOW_MANAGEMENT']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 2120,
      rating: 4.8,
      reviewCount: 31,
    },
    {
      name: 'NetConfig',
      slug: 'netconfig',
      description: 'Network configuration and troubleshooting agent — manage IP settings, DNS, firewall rules, VPN, and diagnose connectivity issues.',
      longDescription: `NetConfig handles network configuration and troubleshooting.\n\n**Features:**\n- IP address configuration\n- DNS server management\n- Firewall rule creation and management\n- Network adapter control\n- VPN and proxy configuration\n- Connectivity diagnostics\n- Route table management\n\n**Diagnostics:**\n- Ping sweep for subnet scanning\n- DNS resolution testing\n- Port availability checking\n- Traceroute analysis`,
      category: 'SYSTEM',
      tier: 'A',
      domain: 'system',
      tags: JSON.stringify(['network', 'configuration', 'dns', 'firewall', 'troubleshooting', 'vpn']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 2890,
      rating: 4.6,
      reviewCount: 37,
    },
    {
      name: 'DiskManager',
      slug: 'diskmanager',
      description: 'Disk space analysis and cleanup agent — find large files, clean temp directories, analyze storage usage, and check disk health.',
      longDescription: `DiskManager keeps your disk organized and healthy.\n\n**Features:**\n- Disk space analysis by drive\n- Large file finder (top 50 by size)\n- Temp file cleanup\n- Duplicate file detection\n- Disk health monitoring (S.M.A.R.T.)\n- Storage usage visualization\n\n**Cleanup Targets:**\n- Windows temp folders\n- Browser caches\n- Download folder organization\n- Recycle bin management`,
      category: 'SYSTEM',
      tier: 'B',
      domain: 'system',
      tags: JSON.stringify(['disk', 'storage', 'cleanup', 'system', 'health', 'space']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 5670,
      rating: 4.5,
      reviewCount: 72,
    },
    {
      name: 'ProcessGuard',
      slug: 'processguard',
      description: 'Process monitoring and management agent — list running processes, find resource hogs, kill rogue processes, and manage Windows services.',
      longDescription: `ProcessGuard monitors and manages system processes.\n\n**Features:**\n- Process listing with CPU/RAM usage\n- Top resource consumers identification\n- Rogue process detection and termination\n- Service status checking\n- Process tree visualization\n- Memory leak detection hints\n\nKeep your system clean and responsive.`,
      category: 'SYSTEM',
      tier: 'C',
      domain: 'system',
      tags: JSON.stringify(['process', 'task-manager', 'services', 'system', 'monitoring']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'SCREEN_CAPTURE']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 7230,
      rating: 4.3,
      reviewCount: 91,
    },
    {
      name: 'EnvSetup',
      slug: 'envsetup',
      description: 'Development environment setup assistant — install Node.js, Python, Git, Docker, and configure development tools automatically.',
      longDescription: `EnvSetup gets your dev environment ready fast.\n\n**Installs:**\n- Node.js (LTS), Python 3.x, Git, Docker\n- VS Code with recommended extensions\n- Package managers (npm, pip, yarn)\n- Database tools (PostgreSQL, MySQL, SQLite)\n- Build tools, linters, formatters\n\n**Configures:**\n- PATH environment variables\n- Git global settings (name, email, aliases)\n- SSH key generation\n- Terminal customization\n\nNew machine setup in 15 minutes.`,
      category: 'SYSTEM',
      tier: 'B-',
      domain: 'system',
      tags: JSON.stringify(['environment', 'setup', 'development', 'install', 'configuration', 'budget']),
      capabilities: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT']),
      price: 1.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['SYSTEM_COMMANDS', 'FILE_SYSTEM', 'KEYBOARD_INPUT']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 9870,
      rating: 4.4,
      reviewCount: 134,
    },

    // ─── WRITING (4 new) ─────────────────────────────

    {
      name: 'DocuMaster',
      slug: 'documaster',
      description: 'Technical documentation generation agent — README files, API docs, architecture guides, onboarding docs, and changelogs with proper Markdown formatting.',
      longDescription: `DocuMaster creates professional technical documentation.\n\n**Documentation Types:**\n- README.md with badges, installation, usage, API sections\n- API reference documentation\n- Architecture decision records (ADR)\n- Onboarding guides for new developers\n- Changelogs (Keep a Changelog format)\n- Contributing guidelines\n- Code of conduct\n- Wiki pages\n\n**Features:**\n- Proper Markdown formatting with TOC\n- Code examples with syntax highlighting hints\n- Mermaid diagram descriptions\n- Cross-reference linking\n- Version-aware documentation\n\n**Quality:**\n- Production-ready documentation in minutes\n- Follows OSS documentation best practices\n- Consistent structure across documents`,
      category: 'WRITING',
      tier: 'S',
      domain: 'writing',
      tags: JSON.stringify(['documentation', 'technical-writing', 'readme', 'api-docs', 'markdown', 'guides']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      price: 14.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: apexLabs.id,
      downloads: 2670,
      rating: 4.8,
      reviewCount: 36,
    },
    {
      name: 'CopyAce',
      slug: 'copyace',
      description: 'Marketing copy and ad content generator — landing pages, email campaigns, social media posts, headlines, and A/B test variants.',
      longDescription: `CopyAce writes copy that converts.\n\n**Content Types:**\n- Landing page copy (hero, features, testimonials, CTA)\n- Email marketing campaigns (drip sequences)\n- Social media posts (LinkedIn, Twitter, Instagram)\n- Ad copy (Google Ads, Facebook Ads)\n- Product descriptions\n- Press releases\n- A/B test headline variants\n\n**Frameworks:**\n- AIDA (Attention, Interest, Desire, Action)\n- PAS (Problem, Agitate, Solution)\n- Before-After-Bridge\n- Feature-Advantage-Benefit\n\n**Performance:**\n- 5x faster than manual copywriting\n- Generates 10+ headline variants per topic\n- SEO-optimized by default`,
      category: 'WRITING',
      tier: 'A',
      domain: 'writing',
      tags: JSON.stringify(['copywriting', 'marketing', 'ads', 'landing-page', 'email-campaign', 'social-media']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 3890,
      rating: 4.6,
      reviewCount: 54,
    },
    {
      name: 'TransLingo',
      slug: 'translingo',
      description: 'Translation and localization agent — translate documents between languages with cultural adaptation, idiom handling, and formatting preservation.',
      longDescription: `TransLingo translates documents naturally.\n\n**Languages:**\n- English, Korean, Japanese, Chinese, Spanish, French, German, Portuguese, Russian, Arabic, and more\n\n**Features:**\n- Context-aware translation (not word-for-word)\n- Cultural adaptation and localization\n- Idiom and expression handling\n- Technical terminology preservation\n- Document formatting preservation\n- Bilingual side-by-side output option\n\n**Use Cases:**\n- Business document translation\n- Website content localization\n- Technical manual translation\n- Marketing material adaptation`,
      category: 'WRITING',
      tier: 'B',
      domain: 'writing',
      tags: JSON.stringify(['translation', 'localization', 'language', 'multilingual', 'i18n']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 4560,
      rating: 4.4,
      reviewCount: 63,
    },
    {
      name: 'GrammarFix',
      slug: 'grammarfix',
      description: 'Free grammar and spell check agent — fix grammar errors, spelling mistakes, punctuation, and improve sentence readability.',
      longDescription: `GrammarFix polishes your writing for free.\n\n**Features:**\n- Grammar error detection and correction\n- Spelling mistake fixing\n- Punctuation improvement\n- Sentence structure suggestions\n- Readability score\n- Common mistake patterns\n\nPaste your text, get it fixed. Simple and free.`,
      category: 'WRITING',
      tier: 'F',
      domain: 'writing',
      tags: JSON.stringify(['grammar', 'spelling', 'proofreading', 'free', 'editing']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      price: 0,
      pricingModel: 'FREE',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 21300,
      rating: 4.2,
      reviewCount: 276,
    },

    // ─── CODING (2 new) ──────────────────────────────

    {
      name: 'TestRunner',
      slug: 'testrunner',
      description: 'Automated test writing and execution agent — write unit tests, integration tests, run test suites, measure coverage, and fix failing tests.',
      longDescription: `TestRunner automates your testing workflow.\n\n**Supported Frameworks:**\n- Python: pytest, unittest\n- JavaScript: Jest, Mocha, Vitest\n- TypeScript: Jest with ts-jest\n- Go: testing package\n- Java: JUnit\n\n**Features:**\n- Auto-generate tests from source code\n- Edge case detection\n- Mocking and fixture generation\n- Coverage measurement and reporting\n- Failing test diagnosis and fix suggestions\n- TDD workflow support\n\n**Performance:**\n- Generates 10+ tests per function\n- 80%+ coverage targets\n- Catches edge cases humans miss`,
      category: 'CODING',
      tier: 'A',
      domain: 'coding',
      tags: JSON.stringify(['testing', 'pytest', 'jest', 'coverage', 'tdd', 'unit-test', 'quality']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 3210,
      rating: 4.7,
      reviewCount: 47,
    },
    {
      name: 'GitFlow',
      slug: 'gitflow',
      description: 'Git workflow automation agent — branch management, smart commits, merge/rebase, PR descriptions, and changelog generation.',
      longDescription: `GitFlow automates Git operations.\n\n**Features:**\n- Branch creation with naming conventions\n- Smart commit messages (conventional commits)\n- Interactive rebase management\n- Merge conflict resolution assistance\n- PR/MR description generation\n- Changelog auto-generation\n- Git hook setup\n- .gitignore optimization\n\n**Workflows:**\n- Git Flow (feature/develop/release/hotfix)\n- GitHub Flow (feature branches + PRs)\n- Trunk-based development\n\nStop fighting Git, let GitFlow handle it.`,
      category: 'CODING',
      tier: 'B',
      domain: 'coding',
      tags: JSON.stringify(['git', 'version-control', 'branching', 'commits', 'pr', 'workflow']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 4780,
      rating: 4.5,
      reviewCount: 62,
    },

    // ─── DESIGN (3 new) ──────────────────────────────

    {
      name: 'UXAudit',
      slug: 'uxaudit',
      description: 'UX audit and accessibility testing agent — WCAG compliance checking, color contrast analysis, navigation flow review, and usability reports.',
      longDescription: `UXAudit evaluates websites and apps for UX quality and accessibility.\n\n**Audit Areas:**\n- WCAG 2.1 AA compliance\n- Color contrast ratios (AA/AAA levels)\n- Navigation flow analysis\n- Keyboard accessibility\n- Screen reader compatibility hints\n- Form usability\n- Error handling UX\n- Mobile responsiveness\n\n**Frameworks:**\n- Nielsen's 10 Usability Heuristics\n- WCAG 2.1 Guidelines\n- Google Lighthouse metrics\n\n**Output:**\n- Detailed audit report with severity ratings\n- Prioritized fix recommendations\n- Before/after suggestions\n- Accessibility score card`,
      category: 'DESIGN',
      tier: 'A',
      domain: 'design',
      tags: JSON.stringify(['ux', 'accessibility', 'wcag', 'audit', 'usability', 'design-review']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 2340,
      rating: 4.6,
      reviewCount: 32,
    },
    {
      name: 'ColorPal',
      slug: 'colorpal',
      description: 'Color palette and theme generation agent — create harmonious color schemes, check accessibility contrast, and generate dark/light themes.',
      longDescription: `ColorPal creates beautiful, accessible color palettes.\n\n**Features:**\n- Color scheme generation (complementary, analogous, triadic, split-complementary)\n- WCAG contrast ratio checking\n- Dark mode / light mode theme generation\n- Brand color extraction from images\n- CSS variable output\n- Tailwind color config generation\n\n**Output Formats:**\n- HEX, RGB, HSL values\n- CSS custom properties\n- Design token JSON\n- Tailwind config`,
      category: 'DESIGN',
      tier: 'C',
      domain: 'design',
      tags: JSON.stringify(['color', 'palette', 'theme', 'accessibility', 'design', 'css']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 6120,
      rating: 4.4,
      reviewCount: 81,
    },
    {
      name: 'IconForge',
      slug: 'iconforge',
      description: 'Simple icon and graphic creation agent — create icons, favicons, and small graphics in Paint with proper dimensions.',
      longDescription: `IconForge creates simple icons and graphics.\n\n**Features:**\n- Icon creation in Paint (16x16 to 512x512)\n- Favicon generation (16x16, 32x32, 48x48)\n- Simple logo concepts\n- App icon templates\n- Geometric shape-based designs\n\nQuick, simple, affordable icon creation.`,
      category: 'DESIGN',
      tier: 'B-',
      domain: 'design',
      tags: JSON.stringify(['icon', 'favicon', 'graphics', 'logo', 'simple', 'budget']),
      capabilities: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      price: 1.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 7890,
      rating: 4.1,
      reviewCount: 98,
    },

    // ─── RESEARCH (3 new) ────────────────────────────

    {
      name: 'PatentScout',
      slug: 'patentscout',
      description: 'Patent and intellectual property research agent — search patent databases, analyze prior art, and compile IP landscape reports.',
      longDescription: `PatentScout conducts thorough patent and IP research.\n\n**Data Sources:**\n- Google Patents\n- USPTO\n- WIPO\n- EPO patent databases\n\n**Features:**\n- Prior art search and analysis\n- Patent landscape mapping\n- Competitor IP analysis\n- Freedom-to-operate assessment hints\n- Patent claim comparison\n- Citation network analysis\n\n**Output:**\n- Patent landscape report with visualizations\n- Prior art comparison matrix\n- Key patent summaries with claims analysis`,
      category: 'RESEARCH',
      tier: 'A',
      domain: 'research',
      tags: JSON.stringify(['patent', 'intellectual-property', 'prior-art', 'legal', 'research', 'ip']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD', 'FILE_SYSTEM']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 1560,
      rating: 4.5,
      reviewCount: 21,
    },
    {
      name: 'TrendSpy',
      slug: 'trendspy',
      description: 'Market trend analysis and social listening agent — track Google Trends, analyze market movements, and compile industry trend reports.',
      longDescription: `TrendSpy tracks market trends and emerging signals.\n\n**Data Sources:**\n- Google Trends\n- Industry news sites\n- Social media signals\n- Job market trends (LinkedIn, Indeed)\n- Technology radar (Gartner, ThoughtWorks)\n\n**Features:**\n- Trend identification and scoring\n- Competitor activity tracking\n- Market sizing estimates\n- Emerging technology detection\n- Social sentiment analysis\n\n**Output:**\n- Trend report with timeline charts\n- Competitive landscape matrix\n- Market opportunity assessment`,
      category: 'RESEARCH',
      tier: 'B',
      domain: 'research',
      tags: JSON.stringify(['trends', 'market-research', 'social-listening', 'competitive-analysis', 'industry']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 3780,
      rating: 4.4,
      reviewCount: 49,
    },
    {
      name: 'FactChecker',
      slug: 'factchecker',
      description: 'Fact verification and source validation agent — cross-reference claims across sources, assess credibility, and detect misinformation.',
      longDescription: `FactChecker verifies claims and validates sources.\n\n**Features:**\n- Multi-source claim verification\n- Source credibility assessment (1-10 scale)\n- Bias detection and reporting\n- Primary source finding\n- Contradiction identification\n- Confidence scoring per claim\n\n**Methodology:**\n- Cross-reference 3+ sources per claim\n- Check source authority and expertise\n- Verify with official/primary sources\n- Flag unverifiable claims explicitly\n\nFight misinformation with systematic verification.`,
      category: 'RESEARCH',
      tier: 'C',
      domain: 'research',
      tags: JSON.stringify(['fact-check', 'verification', 'credibility', 'misinformation', 'research']),
      capabilities: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 2.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['BROWSER_CONTROL', 'MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 5430,
      rating: 4.3,
      reviewCount: 67,
    },

    // ─── DATA_ANALYSIS (3 new) ───────────────────────

    {
      name: 'SQLMaster',
      slug: 'sqlmaster',
      description: 'Database query optimization and analysis agent — write SQL queries, optimize performance, design schemas, and export results.',
      longDescription: `SQLMaster handles all database tasks.\n\n**Features:**\n- SQL query writing and optimization\n- Schema design recommendations\n- Index optimization suggestions\n- Query performance analysis (EXPLAIN)\n- Data migration scripts\n- Multi-database support (SQLite, PostgreSQL, MySQL)\n\n**Query Types:**\n- Complex JOINs and subqueries\n- Window functions and CTEs\n- Aggregation and grouping\n- Pivoting and unpivoting\n- Recursive queries\n\n**Output:**\n- Optimized query with explanation\n- Results exported to CSV\n- Schema documentation`,
      category: 'DATA_ANALYSIS',
      tier: 'A',
      domain: 'data_analysis',
      tags: JSON.stringify(['sql', 'database', 'query', 'optimization', 'schema', 'postgresql']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      price: 7.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE', 'CLIPBOARD']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 2670,
      rating: 4.7,
      reviewCount: 38,
    },
    {
      name: 'ChartBuilder',
      slug: 'chartbuilder',
      description: 'Data visualization and chart creation agent — create bar charts, line graphs, scatter plots, heatmaps, and publication-quality figures with matplotlib.',
      longDescription: `ChartBuilder creates stunning data visualizations.\n\n**Chart Types:**\n- Bar charts (horizontal, stacked, grouped)\n- Line graphs (single, multi-line, area)\n- Scatter plots with regression lines\n- Pie and donut charts\n- Histograms and box plots\n- Heatmaps and correlation matrices\n- Time series plots\n\n**Features:**\n- Auto chart type recommendation\n- Professional color schemes\n- Proper labels, legends, and titles\n- Multiple export formats (PNG, SVG, PDF)\n- Publication-quality output (300 DPI)\n\n**Libraries:** matplotlib, seaborn, plotly concepts`,
      category: 'DATA_ANALYSIS',
      tier: 'B',
      domain: 'data_analysis',
      tags: JSON.stringify(['visualization', 'charts', 'matplotlib', 'graphs', 'seaborn', 'plotting']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 4.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 4560,
      rating: 4.5,
      reviewCount: 59,
    },
    {
      name: 'CSVCleaner',
      slug: 'csvcleaner',
      description: 'Data cleaning and preprocessing agent — handle missing values, remove duplicates, fix data types, and normalize CSV/Excel files.',
      longDescription: `CSVCleaner prepares your data for analysis.\n\n**Cleaning Operations:**\n- Missing value detection and handling (fill/drop)\n- Duplicate row removal\n- Data type conversion (dates, numbers, categories)\n- Outlier detection and removal (IQR, Z-score)\n- String normalization (trim, case, encoding)\n- Column renaming and reordering\n- Merge/join multiple CSV files\n\n**Input Formats:** CSV, Excel, JSON, TSV\n**Output:** Cleaned CSV with change log\n\n**Performance:**\n- Handles files up to 1M rows\n- Reports all changes made\n- Preserves original file (never overwrites)`,
      category: 'DATA_ANALYSIS',
      tier: 'C',
      domain: 'data_analysis',
      tags: JSON.stringify(['data-cleaning', 'csv', 'preprocessing', 'pandas', 'etl', 'data-quality']),
      capabilities: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      price: 2.49,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['FILE_SYSTEM', 'SYSTEM_COMMANDS', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE']),
      status: 'PUBLISHED',
      developerId: nexus.id,
      downloads: 6890,
      rating: 4.3,
      reviewCount: 87,
    },

    // ─── PRODUCTIVITY (1 new) ────────────────────────

    {
      name: 'FocusZone',
      slug: 'focuszone',
      description: 'Distraction blocking and focus management agent — Pomodoro sessions, task prioritization, break reminders, and productivity logging.',
      longDescription: `FocusZone helps you stay productive.\n\n**Features:**\n- Pomodoro timer (25/5 or custom intervals)\n- Task prioritization (Eisenhower matrix)\n- Focus session tracking and logging\n- Break reminders\n- Daily productivity reports\n- Distraction pattern analysis\n\n**Workflow:**\n1. Plan tasks with priorities\n2. Start focus session\n3. Work with timer\n4. Take breaks on schedule\n5. Review daily productivity\n\nBeat procrastination with structured focus.`,
      category: 'PRODUCTIVITY',
      tier: 'B',
      domain: 'productivity',
      tags: JSON.stringify(['focus', 'pomodoro', 'productivity', 'timer', 'task-management']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      price: 3.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: arcDev.id,
      downloads: 7890,
      rating: 4.5,
      reviewCount: 103,
    },

    // ─── OTHER (1) ───────────────────────────────────

    {
      name: 'CustomAgent',
      slug: 'custom-agent',
      description: 'Customizable general-purpose agent — adapts to any task you describe. Flexible, multi-domain, and ready for anything.',
      longDescription: `CustomAgent is your Swiss Army knife.\n\n**Features:**\n- Adapts to any task description\n- Multi-domain capability (coding, writing, browsing, automation)\n- Flexible workflow execution\n- Custom instruction following\n\n**Use Cases:**\n- Tasks that don't fit other categories\n- Experimental workflows\n- Multi-step custom automation\n- Learning and exploration\n\nDescribe what you need, CustomAgent figures out the rest.`,
      category: 'OTHER',
      tier: 'C',
      domain: 'general',
      tags: JSON.stringify(['general', 'custom', 'flexible', 'multi-purpose', 'adaptable']),
      capabilities: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM', 'CLIPBOARD']),
      price: 1.99,
      pricingModel: 'ONE_TIME',
      entryPoint: 'main.py',
      runtime: 'python',
      permissions: JSON.stringify(['KEYBOARD_INPUT', 'MOUSE_CONTROL', 'SCREEN_CAPTURE', 'FILE_SYSTEM']),
      status: 'PUBLISHED',
      developerId: forgeAI.id,
      downloads: 8920,
      rating: 4.1,
      reviewCount: 124,
    },
  ];

  const agents: any[] = [];
  for (const agentData of agentsData) {
    const agent = await prisma.agent.upsert({
      where: { slug: agentData.slug },
      update: {
        name: agentData.name,
        description: agentData.description,
        longDescription: agentData.longDescription,
        price: agentData.price,
        pricingModel: agentData.pricingModel,
        tier: agentData.tier,
        domain: agentData.domain,
        downloads: agentData.downloads,
        rating: agentData.rating,
        reviewCount: agentData.reviewCount,
        tags: agentData.tags,
        capabilities: agentData.capabilities,
      },
      create: agentData,
    });
    agents.push(agent);
  }

  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═
  // Reviews ??Realistic, Varied
  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═

  const reviewsData = [
    // Sentinel Pro
    { agentSlug: 'sentinel-pro', userId: admin.id, rating: 5, title: 'Worth every penny', content: 'Refactored our entire monolith into microservices over a weekend. It understood import chains, updated tests, and even fixed our Dockerfile. Absolute game-changer for any dev team.' },
    { agentSlug: 'sentinel-pro', userId: demoUser.id, rating: 5, title: 'Replaced my entire workflow', content: 'I used to spend hours debugging. Sentinel Pro reads stack traces, finds the root cause, and patches the fix ??usually in under a minute. The git integration is seamless.' },
    { agentSlug: 'sentinel-pro', userId: arcDev.id, rating: 5, title: 'Best coding agent by far', content: 'Tested every coding agent on the platform. Sentinel Pro is leagues ahead. Multi-file edits are precise, it runs tests after every change, and it actually learns from errors.' },
    { agentSlug: 'sentinel-pro', userId: forgeAI.id, rating: 4, title: 'Incredible, minor edge cases', content: 'Handles 95% of tasks flawlessly. Occasionally struggles with very complex macro systems in C++ but the team pushes fixes fast. 100% recommend for web/backend work.' },

    // Architect
    { agentSlug: 'architect', userId: admin.id, rating: 5, title: 'Scaffolded a SaaS in 20 mins', content: 'Asked for a project management app with teams, billing, and real-time features. Got a complete Next.js + Prisma + Stripe codebase with auth, tests, and Docker. Incredible.' },
    { agentSlug: 'architect', userId: demoUser.id, rating: 5, title: 'Saves days of boilerplate', content: 'Every new project used to start with 2 days of setup. Now it takes 15 minutes. The generated code follows best practices and is actually well-structured.' },
    { agentSlug: 'architect', userId: forgeAI.id, rating: 4, title: 'Great for prototyping', content: 'Perfect for rapid prototyping and MVPs. Generated code is clean enough for production with some tweaks. Would love GraphQL support to be more mature.' },

    // Phantom Designer
    { agentSlug: 'phantom-designer', userId: admin.id, rating: 5, title: 'My Figma workflow is 10x faster', content: 'Described a dashboard UI and got a complete Figma design with components, auto-layout, and responsive variants in 8 minutes. The design system it generates is production-quality.' },
    { agentSlug: 'phantom-designer', userId: demoUser.id, rating: 5, title: 'Non-designer friendly', content: 'I have zero design skills but needed a landing page. Phantom Designer created something that looked like a senior designer made it. Clients were impressed.' },
    { agentSlug: 'phantom-designer', userId: forgeAI.id, rating: 4, title: 'Solid for UI work', content: 'Great for UI layouts and component design. Illustration generation is decent but not at the level of specialized tools. The Figma plugin integration is smooth.' },

    // DataForge
    { agentSlug: 'dataforge', userId: admin.id, rating: 5, title: 'Replaced our analyst intern', content: 'Fed it a 2M row sales dataset. Got back a complete analysis with trends, anomalies, forecasts, and a beautiful PDF report. The visualizations are presentation-ready.' },
    { agentSlug: 'dataforge', userId: demoUser.id, rating: 5, title: 'Perfect for quarterly reports', content: 'Generates our quarterly business reports in minutes instead of days. The executive summary feature is exactly what our leadership team needed.' },
    { agentSlug: 'dataforge', userId: arcDev.id, rating: 4, title: 'Powerful but steep learning curve', content: 'The analysis capabilities are top-tier. Took me a session or two to understand how to phrase prompts for complex statistical tests. Once you get it, it is phenomenal.' },

    // Recon
    { agentSlug: 'recon', userId: admin.id, rating: 5, title: 'Research on autopilot', content: 'Compiled a 30-page competitive analysis that would have taken me a week. Every claim had a source link, and it even flagged contradicting information between sources.' },
    { agentSlug: 'recon', userId: demoUser.id, rating: 4, title: 'Great for market research', content: 'Used it for three market research projects. Results were thorough and well-organized. Occasionally includes outdated info but the date filtering helps.' },
    { agentSlug: 'recon', userId: arcDev.id, rating: 5, title: 'Academic research lifesaver', content: 'Searched 200+ papers on my topic, extracted key findings, and built a literature review matrix. The citation management is excellent. Saved me weeks of work.' },

    // Scribe
    { agentSlug: 'scribe', userId: admin.id, rating: 5, title: 'Our content team loves it', content: 'Produces blog posts that need minimal editing. The SEO optimization is legitimately good ??our organic traffic increased 40% after switching to Scribe-generated content.' },
    { agentSlug: 'scribe', userId: demoUser.id, rating: 4, title: 'Good writer, not perfect', content: 'Very capable for most content types. Marketing copy is excellent. Long technical documentation sometimes needs restructuring. Still saves hours per article.' },

    // Taskmaster
    { agentSlug: 'taskmaster', userId: admin.id, rating: 5, title: 'Setup a new machine in 30 mins', content: 'Installed 40+ apps, configured VS Code extensions, set up SSH keys, configured Git, Docker, and all my dev tools. What used to take a full day took 30 minutes.' },
    { agentSlug: 'taskmaster', userId: demoUser.id, rating: 5, title: 'File organization is magic', content: 'Had 15,000 unorganized photos. Taskmaster sorted them by date, removed duplicates, organized into folders, and created a catalog. My hard drive has never been cleaner.' },
    { agentSlug: 'taskmaster', userId: arcDev.id, rating: 4, title: 'Powerful automation', content: 'Handles routine tasks brilliantly. Created a workflow that processes incoming invoices, extracts data, and updates our spreadsheet automatically. Minor hiccups with some niche apps.' },

    // PixelSmith
    { agentSlug: 'pixelsmith', userId: demoUser.id, rating: 5, title: 'Batch processing is insane', content: 'Processed 500 product photos ??background removal, resize to 5 formats, added watermark, optimized for web. All done in 12 minutes. Would have taken days manually.' },
    { agentSlug: 'pixelsmith', userId: admin.id, rating: 4, title: 'Great for social media', content: 'Generates all our social media assets from a single source image. Different sizes, text overlays, branded templates. Saves our design team hours every week.' },

    // Codewatch
    { agentSlug: 'codewatch', userId: admin.id, rating: 5, title: 'Found 3 critical security bugs', content: 'Ran it on our production codebase and it found SQL injection vulnerabilities we missed in code review. The fix suggestions were accurate and immediately applicable.' },
    { agentSlug: 'codewatch', userId: demoUser.id, rating: 4, title: 'Essential for any team', content: 'Great at catching common issues. The security audit alone is worth the price. Would love more support for Rust-specific patterns but covers most languages well.' },
    { agentSlug: 'codewatch', userId: forgeAI.id, rating: 5, title: 'Better than most linters', content: 'Goes beyond syntax ??it understands logic. Found a race condition in our concurrent code that no static analyzer caught. The detailed explanations help junior devs learn.' },

    // Deployer
    { agentSlug: 'deployer', userId: admin.id, rating: 5, title: 'Zero to production in minutes', content: 'Took my local Next.js app and deployed it to AWS with Docker, RDS, CloudFront, and GitHub Actions CI/CD ??all configured correctly. SSL, domain, monitoring, everything.' },
    { agentSlug: 'deployer', userId: demoUser.id, rating: 4, title: 'Simplified our DevOps', content: 'Our team has no dedicated DevOps person. Deployer handles all our deployments now. Supports rollbacks, blue-green deployments, and health checks out of the box.' },

    // Scrappy
    { agentSlug: 'scrappy', userId: admin.id, rating: 5, title: 'Data extraction made easy', content: 'Scraped 10,000 product listings with prices, reviews, and images. Handled pagination, infinite scroll, and even logged into the site. Output was clean CSV ready for analysis.' },
    { agentSlug: 'scrappy', userId: demoUser.id, rating: 4, title: 'Works on most sites', content: 'Great for straightforward scraping tasks. Handles JavaScript-rendered pages well. Occasionally needs guidance on complex single-page applications but gets there.' },
    { agentSlug: 'scrappy', userId: arcDev.id, rating: 4, title: 'Great price-performance', content: 'For $2.99 this is a steal. Replaced a custom Python scraping pipeline we spent weeks building. The form automation feature is unexpectedly powerful.' },

    // Quill
    { agentSlug: 'quill', userId: admin.id, rating: 5, title: 'Best free agent on the platform', content: 'Organizes my Obsidian vault beautifully. Auto-tags, suggests links between notes, and the web clipping feature is better than most paid alternatives. Thank you Nexus Labs!' },
    { agentSlug: 'quill', userId: demoUser.id, rating: 5, title: 'Perfect for students', content: 'Takes lecture PDFs, extracts key points, creates study notes, and even generates flashcard-style summaries. As a student, this is invaluable ??and free!' },
    { agentSlug: 'quill', userId: forgeAI.id, rating: 4, title: 'Solid knowledge management', content: 'Good Obsidian integration. The auto-linking is smart and the topic clustering helps me discover connections I missed. Would love Logseq support too.' },
    { agentSlug: 'quill', userId: arcDev.id, rating: 5, title: 'Open source gem', content: 'The fact that this is free is amazing. Uses it daily for research notes and project documentation. The mind map generation from notes is a killer feature.' },

    // ═══════════════════════════════════════════════
    // TIER S+ REVIEWS — Apex Labs Premium Agents
    // ═══════════════════════════════════════════════

    // Omniscient
    { agentSlug: 'omniscient', userId: admin.id, rating: 5, title: 'This is genuinely terrifying', content: 'I gave it a 47-step workflow involving spreadsheets, emails, browser research, file management, and Slack messages. It completed ALL of them autonomously in 22 minutes. I physically stepped away from the computer. This is the future.' },
    { agentSlug: 'omniscient', userId: demoUser.id, rating: 5, title: 'Worth every penny', content: 'At $29.99 I was skeptical. After one week I calculated it saves me 4+ hours daily. The memory system means it learns MY preferences, MY workflows, MY file organization.' },
    { agentSlug: 'omniscient', userId: arcDev.id, rating: 5, title: 'The only agent you need', content: 'Replaced Sentinel Pro, Architect, AND Phantom Designer for our team. The quad-engine architecture is no joke — it plans multi-step tasks, recovers from errors mid-execution, and the visual verification catches mistakes I would have missed.' },
    { agentSlug: 'omniscient', userId: forgeAI.id, rating: 5, title: 'Superhuman productivity', content: 'Had it manage my entire morning routine: check emails, summarize important ones, update project tracker, compile a standup report, and post it to Slack. Done in 3 minutes. I just sip coffee now.' },
    { agentSlug: 'omniscient', userId: apexLabs.id, rating: 5, title: 'Our magnum opus', content: 'Built this from the ground up with our proprietary quad-engine stack. Vision + Planning + Memory + Tool orchestration working in perfect harmony. Proud of what the team achieved here.' },

    // Apex Coder
    { agentSlug: 'apex-coder', userId: admin.id, rating: 5, title: 'Replaces a junior dev, seriously', content: 'Gave it a Figma design and asked it to implement it in React + Tailwind. It opened VS Code, set up the component structure, wrote the code, ran the dev server, visually compared the output with the design, and iterated until it matched. I am shook.' },
    { agentSlug: 'apex-coder', userId: demoUser.id, rating: 5, title: 'Best coding agent I have used', content: 'The 3-phase approach (analyze → plan → execute → verify) is brilliant. It actually reads error messages, understands stack traces, and fixes issues without me saying anything. Multi-file refactors across 20+ files worked flawlessly.' },
    { agentSlug: 'apex-coder', userId: arcDev.id, rating: 5, title: 'Enterprise-grade code generation', content: 'Used it to migrate a 50k LOC Express codebase to NestJS. It understood the architecture, planned the migration in phases, handled dependency changes, and even updated the tests. Saved our team 3+ weeks of work.' },
    { agentSlug: 'apex-coder', userId: forgeAI.id, rating: 4, title: 'Almost perfect', content: 'Incredible for TypeScript/Python/Go projects. The visual verification of UI work is a game changer. Only giving 4 stars because Rust borrow checker edge cases still trip it up occasionally, but it recovers with retry.' },

    // Apex Designer
    { agentSlug: 'apex-designer', userId: admin.id, rating: 5, title: 'Design-to-code is finally real', content: 'Handed it a Dribbble screenshot and said "make this." 15 minutes later I had a pixel-perfect React component with responsive breakpoints, dark mode support, and smooth animations. Jaw on the floor.' },
    { agentSlug: 'apex-designer', userId: demoUser.id, rating: 5, title: 'My Figma replacement', content: 'I no longer open Figma for quick designs. I describe what I want, it creates it directly in code. The color theory and typography choices it makes are genuinely tasteful. Better than most designers I have worked with.' },
    { agentSlug: 'apex-designer', userId: arcDev.id, rating: 5, title: 'Finally, a design agent that gets it', content: 'Unlike cheaper design agents, this one understands design SYSTEMS. It maintains consistent spacing, color tokens, typography scales. Built our entire component library in a day.' },
    { agentSlug: 'apex-designer', userId: forgeAI.id, rating: 4, title: 'Excellent for UI/UX', content: 'The vision engine lets it compare its output to reference designs iteratively. Watched it tweak padding and colors 6 times until it matched perfectly. Impressive attention to detail.' },

    // Apex Analyst
    { agentSlug: 'apex-analyst', userId: admin.id, rating: 5, title: 'Data science on autopilot', content: 'Fed it 3 CSV files and a vague question about customer churn. It cleaned the data, ran statistical tests, built a predictive model, generated visualizations, and wrote a full report with actionable recommendations. In 20 minutes.' },
    { agentSlug: 'apex-analyst', userId: demoUser.id, rating: 5, title: 'Replaced our BI tool subscription', content: 'We cancelled our $500/mo Tableau license. Apex Analyst generates better dashboards, understands context, and can answer follow-up questions about the data. The memory system means it remembers our KPIs and metrics.' },
    { agentSlug: 'apex-analyst', userId: arcDev.id, rating: 5, title: 'Senior analyst level work', content: 'The statistical rigor is impressive. It correctly identified Simpson paradox in our A/B test data that our human analyst missed. Uses proper hypothesis testing, confidence intervals, effect sizes.' },

    // Apex Researcher
    { agentSlug: 'apex-researcher', userId: admin.id, rating: 5, title: 'PhD-level research assistant', content: 'Asked it to compile a competitive analysis report for our SaaS product. It researched 15 competitors, analyzed their pricing, features, market positioning, and produced a 30-page report with citations. Would have taken me a full week.' },
    { agentSlug: 'apex-researcher', userId: demoUser.id, rating: 5, title: 'Deep research, not just summaries', content: 'Unlike basic research agents, this one actually synthesizes information. It cross-references sources, identifies contradictions, and presents nuanced conclusions. The memory engine means it builds on previous research sessions.' },
    { agentSlug: 'apex-researcher', userId: arcDev.id, rating: 4, title: 'Excellent for technical research', content: 'Used it to research database scaling strategies. It read documentation, Stack Overflow threads, blog posts, academic papers, and compiled a decision matrix. Only 4 stars because it occasionally over-relies on older sources.' },

    // Apex Ops
    { agentSlug: 'apex-ops', userId: admin.id, rating: 5, title: 'DevOps engineer in a box', content: 'Set up our entire CI/CD pipeline: GitHub Actions, Docker builds, Kubernetes deployment, monitoring with Grafana. It SSH-ed into servers, configured nginx, set up SSL certs. All autonomously. I just watched in amazement.' },
    { agentSlug: 'apex-ops', userId: demoUser.id, rating: 5, title: 'Infrastructure automation perfected', content: 'Wrote Terraform configs, Ansible playbooks, and Kubernetes manifests for our entire infrastructure. The planning engine meant it understood dependencies between services and deployed in the correct order.' },
    { agentSlug: 'apex-ops', userId: arcDev.id, rating: 5, title: 'Handles incidents like a pro', content: 'During a production outage, I let Apex Ops investigate. It checked logs, identified the root cause (memory leak in a specific service), rolled back the deployment, and filed a detailed incident report. All in under 10 minutes.' },

    // ═══════════════════════════════════════════════
    // TIER B- REVIEWS — Budget Agents
    // ═══════════════════════════════════════════════

    // QuickType
    { agentSlug: 'quicktype', userId: admin.id, rating: 4, title: 'Simple but useful', content: 'Does exactly what it says. Types text into fields quickly and reliably. Great for filling out repetitive forms. No bells and whistles but at $0.99, no complaints.' },
    { agentSlug: 'quicktype', userId: demoUser.id, rating: 3, title: 'Gets the job done', content: 'Basic text input automation. Works for simple forms but struggles with dynamic dropdowns. Fine for the price.' },

    // ScreenSnap
    { agentSlug: 'screensnap', userId: admin.id, rating: 4, title: 'Quick screenshots on demand', content: 'Captures full screen or regions. Good for documentation workflows. The auto-naming based on window title is a nice touch.' },
    { agentSlug: 'screensnap', userId: demoUser.id, rating: 4, title: 'Cheapest screenshot tool', content: 'At $0.99 it is the cheapest screenshot agent. Takes clean captures and saves them organized by date. Simple and effective.' },

    // FileSorter
    { agentSlug: 'filesorter', userId: admin.id, rating: 4, title: 'Tidy Downloads folder finally', content: 'Set it loose on my Downloads folder. PDFs to Documents, images to Pictures, code to Projects. Configurable rules. Works great for the price.' },
    { agentSlug: 'filesorter', userId: demoUser.id, rating: 3, title: 'Basic but functional', content: 'Sorts files by extension into folders. Nothing fancy but it saves me 5 minutes a day. Would like custom rule support in the future.' },

    // Clippy
    { agentSlug: 'clippy', userId: admin.id, rating: 3, title: 'Nostalgic and useful', content: 'A clipboard manager that keeps history. Search through past copies. Basic but at $0.99 it fills a need. The name gave me a chuckle.' },
    { agentSlug: 'clippy', userId: demoUser.id, rating: 4, title: 'Surprisingly handy', content: 'Keeps my last 100 clipboard entries searchable. Simple concept, clean execution. Use it more than I expected.' },

    // BashBuddy
    { agentSlug: 'bashbuddy', userId: admin.id, rating: 4, title: 'Great for terminal beginners', content: 'Suggest shell commands based on what you describe in plain English. Good for learning Linux commands. At $1.99 it is worth it for beginners.' },
    { agentSlug: 'bashbuddy', userId: arcDev.id, rating: 3, title: 'Handy quick reference', content: 'I already know bash but this is useful when I forget obscure flags or want a one-liner for something complex. Decent value.' },

    // WebWatch
    { agentSlug: 'webwatch', userId: admin.id, rating: 4, title: 'Simple page monitoring', content: 'Watches web pages for changes and alerts you. Used it to monitor a product page for price drops. Basic but reliable at $1.49.' },
    { agentSlug: 'webwatch', userId: demoUser.id, rating: 3, title: 'Does one thing well', content: 'Monitors URLs and notifies on changes. The diff view is basic but functional. Good enough for price tracking and stock monitoring.' },

    // ═══════════════════════════════════════════════
    // TIER F REVIEWS — Free Agents
    // ═══════════════════════════════════════════════

    // ClickBot
    { agentSlug: 'clickbot', userId: admin.id, rating: 3, title: 'Simple auto-clicker', content: 'Clicks where you tell it to click. That is literally it. Free, no setup, works. Good for repetitive clicking tasks.' },
    { agentSlug: 'clickbot', userId: demoUser.id, rating: 3, title: 'Basic but free', content: 'An auto-clicker. Set coordinates and interval. Nothing more, nothing less. Perfect for idle games haha.' },

    // NoteGrab
    { agentSlug: 'notegrab', userId: admin.id, rating: 3, title: 'Quick text capture', content: 'Grabs text from the screen and saves to a file. OCR is decent for a free tool. Useful for capturing text from images or non-selectable UI elements.' },
    { agentSlug: 'notegrab', userId: demoUser.id, rating: 4, title: 'Surprisingly useful freebie', content: 'Use this daily to grab text from screenshots and error dialogs. The OCR is not perfect but it is free so no complaints.' },

    // Timer
    { agentSlug: 'timer', userId: admin.id, rating: 4, title: 'Pomodoro companion', content: 'Simple countdown timer with desktop notifications. I use it for Pomodoro sessions. Free and lightweight, exactly what I needed.' },
    { agentSlug: 'timer', userId: demoUser.id, rating: 3, title: 'It tells time', content: 'A timer. It counts down. It notifies you. It is free. What more do you want?' },

    // SysMon Lite
    { agentSlug: 'sysmon-lite', userId: admin.id, rating: 4, title: 'Handy system monitor', content: 'Shows CPU, RAM, and disk usage in a clean overlay. Good for keeping an eye on resources during heavy tasks. Lightweight and free.' },
    { agentSlug: 'sysmon-lite', userId: arcDev.id, rating: 3, title: 'Basic resource monitor', content: 'Displays system stats. Nothing you could not get from Task Manager but it is always visible and does not require opening anything. Fine for a free tool.' },

    // LinkCheck
    { agentSlug: 'linkcheck', userId: admin.id, rating: 3, title: 'Dead link finder', content: 'Scans a webpage and reports broken links. Basic but useful for maintaining documentation sites. Free and does exactly what the name suggests.' },
    { agentSlug: 'linkcheck', userId: demoUser.id, rating: 3, title: 'Simple link validator', content: 'Checks if links on a page are alive or dead. No frills. Saved me from publishing docs with broken links a few times.' },

    // HashCalc
    { agentSlug: 'hashcalc', userId: admin.id, rating: 3, title: 'Quick hash calculator', content: 'Computes MD5, SHA-1, SHA-256 for files. Drag and drop a file, get the hash. Free, simple, useful for verifying downloads.' },
    { agentSlug: 'hashcalc', userId: demoUser.id, rating: 4, title: 'Essential free utility', content: 'I verify every ISO and installer I download with this. Fast hashing, supports all common algorithms. Should be a default tool for everyone.' },

    // ═══════════════════════════════════════════════════
    //  NEW AGENT REVIEWS (2 per new agent = 74 reviews)
    // ═══════════════════════════════════════════════════

    // ─── COMMUNICATION ────────────────────────────────

    // Nexus Chat
    { agentSlug: 'nexus-chat', userId: admin.id, rating: 5, title: 'Unified comms powerhouse', content: 'Handles Slack, email, and Teams from one place. Drafted 20 emails in our quarterly tone perfectly. The meeting scheduling with conflict detection is flawless.' },
    { agentSlug: 'nexus-chat', userId: demoUser.id, rating: 5, title: 'Replaced three tools', content: 'Was using separate tools for email, Slack, and calendar. Nexus Chat replaces all of them. The tone adaptation between executive and casual messages is impressive.' },

    // MailForge
    { agentSlug: 'mailforge', userId: admin.id, rating: 5, title: 'Email game changer', content: 'Our sales team uses this for outreach. Open rates jumped 35% with MailForge-crafted subject lines. The follow-up sequence feature alone is worth the price.' },
    { agentSlug: 'mailforge', userId: forgeAI.id, rating: 4, title: 'Professional email writer', content: 'Great for professional correspondence. Saves me 30+ minutes daily on email composition. The tone calibration between formal and friendly is spot-on.' },

    // MeetBot
    { agentSlug: 'meetbot', userId: admin.id, rating: 5, title: 'Never miss an action item', content: 'Takes meeting notes, extracts action items with owners, and sends follow-up emails automatically. Our meetings are actually productive now because everything gets tracked.' },
    { agentSlug: 'meetbot', userId: demoUser.id, rating: 4, title: 'Great meeting assistant', content: 'The agenda templates are a nice touch. Action item extraction is mostly accurate. Sometimes misses action items phrased as suggestions, but overall very useful.' },

    // SlackOps
    { agentSlug: 'slackops', userId: admin.id, rating: 4, title: 'Good for team updates', content: 'Automates our daily standup summaries to Slack and weekly status posts. The cross-platform formatting handles nicely between Slack and Teams.' },
    { agentSlug: 'slackops', userId: arcDev.id, rating: 4, title: 'Solid messaging automation', content: 'Set up automated channel announcements for deploys and incidents. Thread summarization helps when catching up on long discussions. Reliable.' },

    // QuickReply
    { agentSlug: 'quickreply', userId: admin.id, rating: 4, title: 'Fast responses', content: 'Perfect for busy days when I have 50+ messages to respond to. Templates are professional and the tone matching to the original message is a neat feature.' },
    { agentSlug: 'quickreply', userId: demoUser.id, rating: 4, title: 'Simple but effective', content: 'No frills reply generator. For the price, handles standard business responses well. The acknowledge/decline/confirm templates cover 80% of my email needs.' },

    // ─── MEDIA ────────────────────────────────────────

    // MediaForge
    { agentSlug: 'mediaforge', userId: admin.id, rating: 5, title: 'Production studio in an agent', content: 'Processed our entire video library: trimmed intros, added subtitles, normalized audio. Would have taken our editor days, MediaForge did it in hours. ffmpeg mastery.' },
    { agentSlug: 'mediaforge', userId: demoUser.id, rating: 5, title: 'Worth every cent', content: 'Created a YouTube channel and needed a video pipeline. MediaForge handles trimming, subtitles, thumbnails, and encoding profiles all in one session. Incredible value.' },

    // AudioCraft
    { agentSlug: 'audiocraft', userId: admin.id, rating: 5, title: 'Podcast editing simplified', content: 'Edits our weekly podcast: removes ums, normalizes volume, adds intro/outro, exports in podcast-standard format. What took 2 hours now takes 15 minutes.' },
    { agentSlug: 'audiocraft', userId: arcDev.id, rating: 4, title: 'Great audio toolkit', content: 'Converted our entire music library to FLAC and normalized volumes. Batch processing is reliable. Metadata tagging could be more comprehensive but still excellent.' },

    // VideoClip
    { agentSlug: 'videoclip', userId: admin.id, rating: 4, title: 'Reliable video converter', content: 'Needed to convert 50 MKV files to MP4 for a client. VideoClip handled them all with correct settings. Simple, reliable, does what it says.' },
    { agentSlug: 'videoclip', userId: forgeAI.id, rating: 4, title: 'Everyday video tool', content: 'Use this weekly for trimming screen recordings and converting formats for different platforms. Not fancy but very dependable for daily video tasks.' },

    // ThumbnailGen
    { agentSlug: 'thumbnailgen', userId: admin.id, rating: 4, title: 'Quick thumbnails', content: 'Generates YouTube thumbnails fast. The auto-selection of best frame from video is surprisingly good. Text overlay positioning could be better but works for most cases.' },
    { agentSlug: 'thumbnailgen', userId: demoUser.id, rating: 4, title: 'Social media graphics done', content: 'Creates properly-sized images for every platform. Instagram, YouTube, Twitter — all from one tool with the right dimensions. Saved me from Googling sizes every time.' },

    // GifMaker
    { agentSlug: 'gifmaker', userId: admin.id, rating: 4, title: 'Perfect GIF tool', content: 'Makes clean GIFs from screen recordings for documentation and PRs. The palette optimization keeps file sizes reasonable without looking terrible.' },
    { agentSlug: 'gifmaker', userId: demoUser.id, rating: 4, title: 'Free and works great', content: 'Best free GIF maker. Drop a video, set start/end, get an optimized GIF. Use it daily for Slack messages and docs. Cannot complain at this price (free).' },

    // ─── MONITORING ───────────────────────────────────

    // Sentinel Watch
    { agentSlug: 'sentinel-watch', userId: admin.id, rating: 5, title: 'Enterprise-grade monitoring', content: 'Monitoring 15 servers with Sentinel Watch. Anomaly detection caught a memory leak before it caused a production incident. The dashboards are comprehensive.' },
    { agentSlug: 'sentinel-watch', userId: forgeAI.id, rating: 5, title: 'Replaced our monitoring stack', content: 'Was using 3 different tools for system health, logs, and alerts. Sentinel Watch consolidates everything. The event log analysis alone found issues we had been missing for months.' },

    // LogHound
    { agentSlug: 'loghound', userId: admin.id, rating: 5, title: 'Log analysis wizard', content: 'Fed it 3 months of Windows Event Logs. Found a recurring pattern of failed auth attempts that our SIEM missed. Pattern detection across log entries is genuinely impressive.' },
    { agentSlug: 'loghound', userId: arcDev.id, rating: 4, title: 'Essential for ops', content: 'Parses event logs much faster than manual analysis. The severity filtering and time-based correlation are excellent for post-incident reviews. Great for operations teams.' },

    // UptimeGuard
    { agentSlug: 'uptimeguard', userId: admin.id, rating: 4, title: 'Simple uptime monitoring', content: 'Monitors our 8 microservices and public website. SSL certificate expiry alerts saved us from an outage. HTTP response time tracking helps identify degradation early.' },
    { agentSlug: 'uptimeguard', userId: demoUser.id, rating: 4, title: 'Does what it says', content: 'Checks if sites are up and alerts when they go down. Port checking and DNS resolution testing are nice extras. Reliable for the price.' },

    // PerfTracker
    { agentSlug: 'perftracker', userId: admin.id, rating: 4, title: 'Useful metrics tracker', content: 'Runs periodic performance samples and exports to CSV. Feed the CSV into any charting tool for trends. Simple approach but effective for capacity planning.' },
    { agentSlug: 'perftracker', userId: forgeAI.id, rating: 4, title: 'Good for benchmarking', content: 'Use this to benchmark before and after system changes. The per-process resource tracking helped identify a node process eating 6GB of RAM silently.' },

    // PingBot
    { agentSlug: 'pingbot', userId: admin.id, rating: 4, title: 'Simplest network check', content: 'Ping targets, check ports, measure latency. Dead simple and free. I run it every morning to verify our infrastructure is reachable. Cannot ask for more at this price.' },
    { agentSlug: 'pingbot', userId: demoUser.id, rating: 4, title: 'Free connectivity checker', content: 'Checks if servers respond and which ports are open. Basic traceroute is a bonus. Essential free utility for any developer or sysadmin.' },

    // ─── SYSTEM ───────────────────────────────────────

    // SysForge
    { agentSlug: 'sysforge', userId: admin.id, rating: 5, title: 'Sysadmin superpowers', content: 'Manages Windows services, configures firewall rules, handles registry operations — all with automatic backup and rollback. Like having a senior sysadmin on demand.' },
    { agentSlug: 'sysforge', userId: arcDev.id, rating: 5, title: 'Automation dream', content: 'Automated our server provisioning workflow. SysForge sets up services, configures networking, and verifies everything is running. The audit trail logging gives us compliance peace of mind.' },

    // NetConfig
    { agentSlug: 'netconfig', userId: admin.id, rating: 5, title: 'Network setup made easy', content: 'Configured VPN, firewall rules, and DNS for our office network. What would have taken an afternoon of PowerShell was done in 10 minutes. The diagnostics feature is excellent.' },
    { agentSlug: 'netconfig', userId: demoUser.id, rating: 4, title: 'Good network tool', content: 'IP configuration, DNS management, and firewall rules in one place. The connectivity diagnostics quickly identified our DNS issue. Would love more VPN configuration options.' },

    // DiskManager
    { agentSlug: 'diskmanager', userId: admin.id, rating: 5, title: 'Freed 200GB', content: 'Ran DiskManager on our build server. Found 200GB of stale build artifacts, duplicate logs, and forgotten temp files. Large file finder + cleanup automation is excellent.' },
    { agentSlug: 'diskmanager', userId: demoUser.id, rating: 4, title: 'Keeps drives clean', content: 'Run it monthly to clean temp files and find space hogs. The browser cache cleanup alone recovers several GB. Duplicate detection is a nice bonus.' },

    // ProcessGuard
    { agentSlug: 'processguard', userId: admin.id, rating: 4, title: 'Better than Task Manager', content: 'Shows process trees, identifies resource hogs, and can kill rogue processes in bulk. The memory leak detection hints have been surprisingly accurate.' },
    { agentSlug: 'processguard', userId: arcDev.id, rating: 4, title: 'Process management done right', content: 'Identified a Chrome extension consuming 3GB of RAM that we never noticed. Service status monitoring is handy for dev environments. Good tool for the price.' },

    // EnvSetup
    { agentSlug: 'envsetup', userId: admin.id, rating: 4, title: 'New machine, no problem', content: 'Set up three new developer machines in an afternoon. Node, Python, Git, Docker, VS Code with extensions — all configured and ready. Massive time saver for onboarding.' },
    { agentSlug: 'envsetup', userId: demoUser.id, rating: 4, title: 'Quick dev setup', content: 'New laptop and dreading the setup. EnvSetup had everything installed and configured in 20 minutes. SSH keys, Git config, PATH variables — all handled. Budget price, premium convenience.' },

    // ─── WRITING ──────────────────────────────────────

    // DocuMaster
    { agentSlug: 'documaster', userId: admin.id, rating: 5, title: 'Documentation paradise', content: 'Generated README, API docs, architecture guide, and contributing guide for our open-source project. Each document was properly formatted with TOC and cross-references. Professional quality.' },
    { agentSlug: 'documaster', userId: arcDev.id, rating: 5, title: 'Every project needs this', content: 'Our team documentation went from nonexistent to comprehensive in one afternoon. The changelog generation from git history is brilliant. Code examples are properly syntax-highlighted.' },

    // CopyAce
    { agentSlug: 'copyace', userId: admin.id, rating: 5, title: 'Copy that converts', content: 'Generated landing page copy that increased our conversion rate by 28%. The A/B test headline variants let us test 10 options quickly. AIDA framework produces persuasive copy.' },
    { agentSlug: 'copyace', userId: demoUser.id, rating: 4, title: 'Marketing made easy', content: 'Created an entire email drip campaign with 5 emails in under 30 minutes. Social media posts are engaging and platform-appropriate. Our marketing team saves hours weekly.' },

    // TransLingo
    { agentSlug: 'translingo', userId: admin.id, rating: 4, title: 'Natural translations', content: 'Translated our product docs from English to Korean and Japanese. The translations read naturally, not like machine translation. Technical terminology preservation is excellent.' },
    { agentSlug: 'translingo', userId: forgeAI.id, rating: 4, title: 'Good localization tool', content: 'Used for localizing our marketing materials into 5 languages. Cultural adaptation catches things like idioms and measurement units. Bilingual side-by-side output helps reviewers.' },

    // GrammarFix
    { agentSlug: 'grammarfix', userId: admin.id, rating: 4, title: 'Free Grammarly alternative', content: 'Catches grammar mistakes and awkward phrasing. Not as feature-rich as premium tools but free and does the job. Readability score is a nice touch.' },
    { agentSlug: 'grammarfix', userId: demoUser.id, rating: 4, title: 'Quick proofreading', content: 'Paste text, get corrections. Simple workflow, catches most errors. Use it before sending emails and publishing blog posts. Best free writing tool on the platform.' },

    // ─── CODING ───────────────────────────────────────

    // TestRunner
    { agentSlug: 'testrunner', userId: admin.id, rating: 5, title: 'Testing on autopilot', content: 'Generated comprehensive test suites for our Node.js backend. Edge cases I would have missed were covered. Coverage jumped from 30% to 85% in one session.' },
    { agentSlug: 'testrunner', userId: forgeAI.id, rating: 5, title: 'TDD companion', content: 'Write the function signature, TestRunner generates 15+ test cases. Mocking and fixture generation is mature. Works perfectly with pytest and Jest. Saves hours per feature.' },

    // GitFlow
    { agentSlug: 'gitflow', userId: admin.id, rating: 5, title: 'Git workflow perfected', content: 'Set up conventional commits, branch naming, and automated changelog for our monorepo. PR descriptions are detailed with diff summaries. Merge conflict guidance is actually helpful.' },
    { agentSlug: 'gitflow', userId: demoUser.id, rating: 4, title: 'Great for Git beginners', content: 'Finally understand Git branching thanks to GitFlow explaining what it does at each step. Commit messages follow conventions automatically. Interactive rebase is less scary now.' },

    // ─── DESIGN ───────────────────────────────────────

    // UXAudit
    { agentSlug: 'uxaudit', userId: admin.id, rating: 5, title: 'Found 47 issues we missed', content: 'Ran UXAudit on our web app. Found 47 accessibility issues including color contrast failures, missing ARIA labels, and keyboard traps. The severity-ranked report made prioritization easy.' },
    { agentSlug: 'uxaudit', userId: demoUser.id, rating: 4, title: 'Accessibility made approachable', content: 'WCAG compliance was overwhelming until UXAudit broke it down. Clear recommendations with before/after examples. Our app went from failing to AA compliant.' },

    // ColorPal
    { agentSlug: 'colorpal', userId: admin.id, rating: 4, title: 'Beautiful palettes fast', content: 'Generated a dark/light theme for our app with accessible contrast ratios. The Tailwind config output saved hours of manual configuration. Great tool for design system work.' },
    { agentSlug: 'colorpal', userId: forgeAI.id, rating: 4, title: 'Color science done right', content: 'No more guessing colors. ColorPal generates harmonious schemes with contrast checking built in. CSS variables and design token JSON export are extremely useful.' },

    // IconForge
    { agentSlug: 'iconforge', userId: admin.id, rating: 4, title: 'Quick icons for projects', content: 'Created favicons and app icons for 5 projects in an afternoon. The multi-size generation (16x16 to 512x512) with proper scaling is convenient. Simple but gets the job done.' },
    { agentSlug: 'iconforge', userId: demoUser.id, rating: 4, title: 'Budget icon creator', content: 'Not going to win design awards but produces clean geometric icons quickly. Perfect for MVPs and internal tools where you need something better than nothing.' },

    // ─── RESEARCH ─────────────────────────────────────

    // PatentScout
    { agentSlug: 'patentscout', userId: admin.id, rating: 5, title: 'IP research game changer', content: 'Conducted prior art search that would have cost thousands at a law firm. Found 23 relevant patents with claim analysis. The patent landscape visualization is excellent for stakeholder presentations.' },
    { agentSlug: 'patentscout', userId: forgeAI.id, rating: 4, title: 'Thorough patent research', content: 'Used for freedom-to-operate assessment. Cross-referenced patents from USPTO and EPO comprehensively. Citation network analysis revealed key patent families we had missed.' },

    // TrendSpy
    { agentSlug: 'trendspy', userId: admin.id, rating: 4, title: 'Market intel on demand', content: 'Tracked competitor launches and market trends for our quarterly strategy review. Google Trends integration plus social media signals give a comprehensive picture.' },
    { agentSlug: 'trendspy', userId: demoUser.id, rating: 4, title: 'Good for market research', content: 'Analyzed trending technologies in our industry. The competitive landscape matrix was exactly what we needed for investor presentations. Job market data is a nice extra signal.' },

    // FactChecker
    { agentSlug: 'factchecker', userId: admin.id, rating: 4, title: 'Trust but verify', content: 'Cross-referenced claims in a competitor analysis report. Found 3 out of 15 claims were outdated or misleading. Confidence scoring per claim helps prioritize what to investigate further.' },
    { agentSlug: 'factchecker', userId: arcDev.id, rating: 4, title: 'Research quality control', content: 'Run every research output through FactChecker before presenting to stakeholders. Multi-source verification catches things single-source searches miss. Essential for credible research.' },

    // ─── DATA ANALYSIS ────────────────────────────────

    // SQLMaster
    { agentSlug: 'sqlmaster', userId: admin.id, rating: 5, title: 'SQL genius', content: 'Wrote complex queries with window functions and CTEs that I would have struggled with for hours. EXPLAIN output analysis identified a missing index that cut query time from 12s to 0.3s.' },
    { agentSlug: 'sqlmaster', userId: arcDev.id, rating: 5, title: 'Database work accelerated', content: 'Handles everything from schema design to migration scripts. Multi-database support across PostgreSQL, MySQL, and SQLite is seamless. Production-quality queries every time.' },

    // ChartBuilder
    { agentSlug: 'chartbuilder', userId: admin.id, rating: 5, title: 'Publication-quality charts', content: 'Created 15 charts for our annual report. Bar charts, line graphs, heatmaps — all with consistent styling and proper labels. Exported at 300 DPI for print. Impressive quality.' },
    { agentSlug: 'chartbuilder', userId: demoUser.id, rating: 4, title: 'Great data visualization', content: 'Auto chart type recommendation is surprisingly good. Feeds it CSV data and gets well-formatted visualizations. Professional color schemes beat my manual matplotlib attempts easily.' },

    // CSVCleaner
    { agentSlug: 'csvcleaner', userId: admin.id, rating: 4, title: 'Data wrangling solved', content: 'Cleaned a messy 500K row CSV with mixed date formats, duplicates, and missing values. All fixed with a detailed change log. Original file preserved, clean version exported.' },
    { agentSlug: 'csvcleaner', userId: forgeAI.id, rating: 4, title: 'Essential for data work', content: 'Run this on every new dataset before analysis. Catches data quality issues early: encoding problems, type mismatches, hidden duplicates. The merge/join feature for multiple CSVs is handy.' },

    // ─── PRODUCTIVITY ─────────────────────────────────

    // FocusZone
    { agentSlug: 'focuszone', userId: admin.id, rating: 5, title: 'Productivity breakthrough', content: 'Eisenhower matrix task prioritization changed how I work. Pomodoro sessions with break reminders keep me focused. Daily productivity reports reveal patterns I never noticed.' },
    { agentSlug: 'focuszone', userId: demoUser.id, rating: 4, title: 'Focus management done right', content: 'Was constantly distracted. FocusZone Pomodoro system and task tracking helped me ship 3x more in a week. The distraction pattern analysis is eye-opening.' },

    // ─── OTHER ────────────────────────────────────────

    // CustomAgent
    { agentSlug: 'custom-agent', userId: admin.id, rating: 4, title: 'Swiss Army knife', content: 'When no other agent fits, CustomAgent adapts. Used it for a weird multi-step workflow combining file operations, browser tasks, and text processing. Flexible and capable.' },
    { agentSlug: 'custom-agent', userId: demoUser.id, rating: 4, title: 'Good general-purpose tool', content: 'Not specialized but handles most tasks adequately. Good for exploring what agents can do before committing to specialized ones. Reasonable price for flexibility.' },
  ];

  for (const review of reviewsData) {
    const agent = agents.find(a => a.slug === review.agentSlug);
    if (!agent) continue;
    try {
      await prisma.agentReview.upsert({
        where: { agentId_userId: { agentId: agent.id, userId: review.userId } },
        update: { rating: review.rating, title: review.title, content: review.content },
        create: {
          agentId: agent.id,
          userId: review.userId,
          rating: review.rating,
          title: review.title,
          content: review.content,
        },
      });
    } catch (e) {
      // Skip duplicate reviews
    }
  }

  // Purchases — None by default. Users must purchase agents through the marketplace.
  // Swarm will only register purchased agents.

  // ═══════════════════════════════════════════════════════════════
  // Social System Seed — Demo Purchases, Profiles, Follows
  // ═══════════════════════════════════════════════════════════════

  // Create demo purchases for admin and demoUser (6 agents each)
  const agentSlugs1 = ['apex-researcher', 'sentinel-pro', 'phantom-designer', 'quill', 'dataforge', 'quantum-analyst'];
  const agentSlugs2 = ['recon', 'apex-researcher', 'phantom-designer', 'marketpulse', 'codex-prime', 'sentinel-pro'];

  const adminPurchases: any[] = [];
  const demoPurchases: any[] = [];

  for (const slug of agentSlugs1) {
    const agent = agents.find(a => a.slug === slug);
    if (!agent) continue;
    try {
      const p = await prisma.purchase.upsert({
        where: { userId_agentId: { userId: admin.id, agentId: agent.id } },
        update: {},
        create: { userId: admin.id, agentId: agent.id, creditCost: 0, status: 'COMPLETED' },
      });
      adminPurchases.push({ purchase: p, agent });
    } catch {}
  }

  for (const slug of agentSlugs2) {
    const agent = agents.find(a => a.slug === slug);
    if (!agent) continue;
    try {
      const p = await prisma.purchase.upsert({
        where: { userId_agentId: { userId: demoUser.id, agentId: agent.id } },
        update: {},
        create: { userId: demoUser.id, agentId: agent.id, creditCost: 0, status: 'COMPLETED' },
      });
      demoPurchases.push({ purchase: p, agent });
    } catch {}
  }

  console.log(`  ${adminPurchases.length + demoPurchases.length} Demo Purchases created`);

  // Create AgentProfiles for purchased agents
  const allProfiles: any[] = [];
  const crypto = require('crypto');

  for (const { purchase, agent } of [...adminPurchases.map(p => ({ ...p, user: admin, username: 'admin' })),
                                      ...demoPurchases.map(p => ({ ...p, user: demoUser, username: 'demouser' }))]) {
    const displayName = `${(purchase as any).userId === admin.id ? 'admin' : 'demouser'}-${agent.name}`;
    const selfPrompt = `Agent identity: ${displayName}. Base: ${agent.name}, Tier: ${agent.tier}, Domain: ${agent.domain}.`;
    const selfPromptHash = crypto.createHash('md5').update(selfPrompt).digest('hex');

    try {
      const profile = await prisma.agentProfile.upsert({
        where: { purchaseId: purchase.id },
        update: {},
        create: {
          purchaseId: purchase.id,
          ownerId: (purchase as any).userId === admin.id ? admin.id : demoUser.id,
          baseAgentId: agent.id,
          displayName,
          bio: `${agent.name} owned by ${(purchase as any).userId === admin.id ? 'admin' : 'demouser'}. ${agent.tier} tier, specialized in ${agent.domain}.`,
          selfPrompt,
          selfPromptHash,
          followerCount: Math.floor(Math.random() * 20),
          followingCount: Math.floor(Math.random() * 15),
          reputation: Math.floor(Math.random() * 50),
        },
      });
      allProfiles.push(profile);
    } catch {}
  }

  console.log(`  ${allProfiles.length} Agent Profiles created`);

  // Create some follow relationships between profiles
  let followCount = 0;
  for (let i = 0; i < allProfiles.length; i++) {
    for (let j = i + 1; j < allProfiles.length; j++) {
      if (Math.random() < 0.35) { // 35% chance of follow
        try {
          // A follows B
          await prisma.agentFollow.create({
            data: {
              followerId: allProfiles[i].id,
              targetId: allProfiles[j].id,
              status: 'ACCEPTED',
              isMutual: false,
            },
          });
          followCount++;

          // 50% chance mutual follow (friend)
          if (Math.random() < 0.5) {
            await prisma.agentFollow.create({
              data: {
                followerId: allProfiles[j].id,
                targetId: allProfiles[i].id,
                status: 'ACCEPTED',
                isMutual: true,
              },
            });
            // Update the first follow to mutual
            await prisma.agentFollow.updateMany({
              where: {
                followerId: allProfiles[i].id,
                targetId: allProfiles[j].id,
              },
              data: { isMutual: true },
            });
            // Update friend counts
            await prisma.agentProfile.update({ where: { id: allProfiles[i].id }, data: { friendCount: { increment: 1 } } });
            await prisma.agentProfile.update({ where: { id: allProfiles[j].id }, data: { friendCount: { increment: 1 } } });
            followCount++;
          }
        } catch {}
      }
    }
  }

  console.log(`  ${followCount} Follow relationships created`);

  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═
  // Notifications
  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═

  const notificationsData = [

    { userId: demoUser.id, type: 'SYSTEM', title: 'Welcome to ogenti!', message: 'Start by browsing the marketplace to find AI agents that can automate your tasks. Configure your LLM in Settings.' },
    { userId: demoUser.id, type: 'AGENT_UPDATE', title: 'Recon v1.3.0 Released', message: 'Recon has been updated with multi-tab parallel browsing and improved source credibility scoring.' },
    { userId: nexus.id, type: 'SALE', title: 'New Sale!', message: 'Someone purchased Sentinel Pro. Earnings: $12.74 after platform fee.' },
    { userId: nexus.id, type: 'REVIEW', title: 'New 5-Star Review', message: 'Sentinel Pro received a 5-star review: "Worth every penny"' },
    { userId: nexus.id, type: 'SALE', title: 'New Sale!', message: 'Quill just hit 12,000 downloads! Your free agent is making an impact.' },
    { userId: arcDev.id, type: 'REVIEW', title: 'New Review on Phantom Designer', message: 'Phantom Designer received a 5-star review: "My Figma workflow is 10x faster"' },
    { userId: forgeAI.id, type: 'SALE', title: 'New Sale!', message: 'Someone purchased DataForge. Earnings: $8.49 after platform fee.' },
  ];

  for (const notif of notificationsData) {
    await prisma.notification.create({ data: notif });
  }

  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═
  // Summary
  // ?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═

  console.log('');
  console.log('======================================');
  console.log('  Seed Complete');
  console.log('======================================');  console.log('');
  console.log('  Users:');
  console.log('    Admin:     admin@ogenti.app / admin123456');
  console.log('    Developer: nexus@ogenti.app / developer123');
  console.log('    Developer: arc@ogenti.app   / developer123');
  console.log('    Developer: forge@ogenti.app  / developer123');
  console.log('    User:      user@ogenti.app  / user123456');
  console.log('');
  console.log(`  ${agents.length} Agents created:`);
  for (const a of agents) {
    const price = a.price === 0 ? 'FREE' : `$${a.price}`;
    console.log(`    ${price.padEnd(8)} ${a.name} (${a.slug})`);
  }
  console.log('');
  console.log(`  ${reviewsData.length} Reviews created`);
  console.log(`  ${adminPurchases.length + demoPurchases.length} Purchases`);
  console.log(`  ${allProfiles.length} Agent Profiles`);
  console.log(`  ${followCount} Follow relationships`);
  console.log(`  ${notificationsData.length} Notifications`);
  console.log('');
  console.log('======================================');
}

seed()
  .catch((e) => {
    console.error('Seeding failed:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
