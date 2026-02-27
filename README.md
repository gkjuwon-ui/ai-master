<div align="center">

<br/>

# ◉ ogenti

### AI Agents That Control Your Operating System

<br/>

[![License](https://img.shields.io/badge/license-Proprietary-black?style=flat-square)](LICENSE)
[![Node](https://img.shields.io/badge/node-%E2%89%A518-black?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.10-black?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Electron](https://img.shields.io/badge/electron-desktop-black?style=flat-square&logo=electron&logoColor=white)](https://electronjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.3-black?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)

<br/>

Discover, build, and run AI agents that directly interact with your computer.  
Mouse control · Keyboard input · App management · All automated by AI.

<br/>

[**Website**](https://ogenti.app) · [**Documentation**](https://ogenti.app/docs) · [**Marketplace**](https://ogenti.app/marketplace) · [**SDK Reference**](https://ogenti.app/docs/sdk) · [**Get Started →**](#-quick-start)

<br/>

---

</div>

<br/>

## Why ogenti?

Operating systems remain the last frontier of AI automation. While AI excels at generating text and images, it still can't natively **use your computer** — open apps, fill forms, navigate workflows, or orchestrate multi-step desktop tasks.

**ogenti changes that.** It's a full-stack platform where AI agents see your screen, move the mouse, type on the keyboard, and manage applications — all in real-time, powered by the LLM of your choice.

Users discover agents on a built-in marketplace. Developers build and monetize them with a TypeScript SDK. Everything runs locally inside a native desktop app.

<br/>

## ✦ Key Features

<table>
<tr>
<td width="50%">

### 🖥️ For Users

- **Agent Marketplace** — Browse, search, and purchase OS-controlling AI agents by category, pricing, and rating
- **Multi-Agent Orchestration** — Chain multiple agents for complex, multi-step workflows
- **Bring Your Own LLM** — OpenAI, Anthropic, Google, Mistral, or any OpenAI-compatible endpoint
- **Real-Time Monitoring** — Watch agents work with live screenshots, execution logs, and status via WebSocket
- **Workspace** — Configure agent parameters, manage sessions, and review results
- **Dashboard** — Track usage analytics, purchase history, and agent performance metrics

</td>
<td width="50%">

### ⚡ For Developers

- **TypeScript SDK** — Build agents with typed `AgentPlugin` base class, manifest config, and testing harness
- **Plugin Architecture** — Python/Node plugins with granular capabilities (mouse, keyboard, screen, filesystem, clipboard, terminal)
- **Developer Portal** — Manage published agents, view download analytics, and handle payouts
- **Flexible Monetization** — Free · One-Time Purchase · Subscription · Usage-Based · Freemium
- **CLI Tooling** — `validate`, `test`, `publish` — zero-friction development workflow
- **Stripe Connect** — Automatic developer payouts with platform fee management

</td>
</tr>
</table>

<br/>

## ◈ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      Electron Desktop Shell                      │
│                                                                  │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│   │   Next.js    │   │   Express    │   │   Python FastAPI   │  │
│   │   Frontend   │◄─►│   Backend    │◄─►│   Agent Runtime    │  │
│   │   (React)    │   │  (REST + WS) │   │   (LLM ↔ OS)      │  │
│   └──────┬───────┘   └──────┬───────┘   └────────┬───────────┘  │
│          │                  │                     │              │
│   Tailwind CSS        SQLite/Prisma         Plugin System       │
│   Zustand State       JWT + Stripe          Screenshot Capture  │
│   Framer Motion       WebSocket Hub         Mouse & Keyboard    │
│   Dark UI System      REST API              App & File Control  │
└──────────────────────────────────────────────────────────────────┘
```

| Layer | Technology | Responsibility |
|:------|:-----------|:---------------|
| **Frontend** | Next.js 14 · React 18 · Tailwind CSS · Zustand | Marketplace, workspace, dashboard, real-time UI |
| **Backend** | Express · Prisma · SQLite · Stripe · JWT | REST API, WebSocket server, auth, payments |
| **Agent Runtime** | Python · FastAPI · asyncio · PyAutoGUI · Pillow | LLM orchestration, OS control, plugin execution |
| **Desktop** | Electron · electron-store | Native shell, process lifecycle management |
| **SDK** | TypeScript · CLI | Agent development, testing, publishing pipeline |

<br/>

## ◆ Tech Stack

| Category | Technologies |
|:---------|:-------------|
| **Frontend** | Next.js 14 · React 18 · TypeScript · Tailwind CSS 3.4 · Zustand · Framer Motion · Lucide Icons · Stripe.js |
| **Backend** | Express · TypeScript · Prisma ORM · SQLite · JWT · Helmet · CORS · Stripe Connect |
| **Runtime** | Python 3.10+ · FastAPI · asyncio · httpx · Pillow · PyAutoGUI · Plugin Loader |
| **Desktop** | Electron · electron-store · Child Process Manager |
| **SDK** | TypeScript · CLI Tools · Agent Testing Framework |
| **DevOps** | Docker · Docker Compose · GitHub Actions · Electron Builder |

<br/>

## ⚑ Quick Start

### Prerequisites

| Requirement | Version |
|:------------|:--------|
| Node.js | ≥ 18.x |
| Python | ≥ 3.10 |
| npm | ≥ 9.x |

### Option 1 — Docker (Recommended)

```bash
git clone https://github.com/ogenti/ogenti.git
cd ogenti
docker compose up --build
```

| Service | URL |
|:--------|:----|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:4000` |
| Agent Runtime | `http://localhost:8000` |

### Option 2 — Manual Setup

<details>
<summary><strong>Step-by-step instructions</strong></summary>

<br/>

**1. Install dependencies**

```bash
# Root workspace (installs all packages via npm workspaces)
npm install

# Agent runtime (Python)
cd agent-runtime
pip install -r requirements.txt
cd ..
```

**2. Initialize database**

```bash
cd backend
npx prisma migrate deploy
npx prisma generate
npx tsx prisma/seed.ts
cd ..
```

**3. Start development servers**

```bash
# All services at once
npm run dev

# — or individually —

# Terminal 1: Backend
cd backend
DATABASE_URL="file:./dev.db" JWT_SECRET="dev-secret" JWT_REFRESH_SECRET="dev-refresh-secret" npx tsx src/server.ts

# Terminal 2: Frontend
cd frontend
npx next dev

# Terminal 3: Agent Runtime
cd agent-runtime
python main.py
```

</details>

### Option 3 — Desktop App (Electron)

```bash
npm run build              # Build all services
cd electron
npm run build:win          # Package for Windows
```

<br/>

## 📂 Project Structure

```
ogenti/
├── frontend/                   Next.js 14 — Marketplace UI & Dashboard
│   ├── src/app/                App Router pages (marketplace, workspace, settings, etc.)
│   ├── src/components/         Reusable React components
│   ├── src/lib/                API client, WebSocket, utilities
│   └── src/store/              Zustand state management
│
├── backend/                    Express — REST API & WebSocket Server
│   ├── src/routes/             API endpoints (agents, auth, execution, payments)
│   ├── src/services/           Business logic layer
│   ├── src/middleware/         Auth, validation, error handling
│   └── prisma/                 Database schema, migrations, seed data
│
├── agent-runtime/              Python FastAPI — Agent Execution Engine
│   ├── core/                   Engine, LLM client, OS controller, screenshot
│   └── plugins/                Built-in agent plugins (coding, design, research)
│
├── electron/                   Desktop Application Shell
│   ├── main.js                 Main process — window & child process management
│   ├── preload.js              Secure bridge between main & renderer
│   └── scripts/                Platform-specific build scripts
│
├── sdk/                        Agent Development SDK
│   ├── src/AgentSDK.ts         SDK client for marketplace interaction
│   ├── src/plugin.ts           AgentPlugin base class
│   ├── src/cli.ts              CLI tools (validate, test, publish)
│   └── src/testing.ts          Agent testing framework
│
├── shared/                     Shared TypeScript types across packages
├── docker-compose.yml          Container orchestration
└── package.json                Monorepo workspace root
```

<br/>

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `DATABASE_URL` | `file:./dev.db` | Prisma database connection string |
| `JWT_SECRET` | — | Secret for JWT access token signing |
| `JWT_REFRESH_SECRET` | — | Secret for JWT refresh token signing |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `NEXT_PUBLIC_API_URL` | `http://localhost:4000` | Backend API URL (client-side) |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:4000` | WebSocket URL (client-side) |
| `NEXT_PUBLIC_STRIPE_KEY` | — | Stripe publishable key |
| `STRIPE_SECRET_KEY` | — | Stripe secret key |
| `RUNTIME_PORT` | `8000` | Agent runtime server port |
| `RUNTIME_HOST` | `0.0.0.0` | Agent runtime bind host |
| `BACKEND_URL` | `http://backend:3001` | Backend URL for runtime callbacks |
| `LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |

### Supported LLM Providers

| Provider | Example Models | Notes |
|:---------|:---------------|:------|
| **OpenAI** | GPT-4o, GPT-4 Turbo, GPT-3.5 Turbo | Default provider |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus | Via API key |
| **Google** | Gemini Pro, Gemini Ultra | Via API key |
| **Mistral** | Mistral Large, Mixtral 8x7B | Via API key |
| **Local** | Any model | Via OpenAI-compatible endpoints (LM Studio, Ollama, vLLM) |

Configure your provider in **Settings → LLM Configuration** within the app.

<br/>

## 🔌 Agent Development

### Creating an Agent

```typescript
import { AgentPlugin, AgentContext } from '@ogenti/sdk';

export default class MyAgent extends AgentPlugin {
  manifest = {
    name: 'My Agent',
    slug: 'my-agent',
    version: '1.0.0',
    description: 'An agent that automates desktop tasks',
    category: 'AUTOMATION',
    capabilities: ['MOUSE_CONTROL', 'KEYBOARD_INPUT', 'SCREEN_CAPTURE'],
    pricingModel: 'FREE',
    runtime: 'python',
  };

  async execute(context: AgentContext): Promise<void> {
    const screenshot = await context.captureScreen();
    await context.moveMouse(100, 200);
    await context.click();
    await context.typeText('Hello from ogenti!');
  }
}
```

### Agent Capabilities

| Capability | Description |
|:-----------|:------------|
| `MOUSE_CONTROL` | Move cursor, click, double-click, drag, scroll |
| `KEYBOARD_INPUT` | Type text, press keys, key combinations |
| `SCREEN_CAPTURE` | Take screenshots, read screen regions |
| `FILE_SYSTEM` | Read, write, move, delete files and directories |
| `CLIPBOARD` | Read from and write to system clipboard |
| `APP_CONTROL` | Launch, focus, minimize, close applications |
| `BROWSER_CONTROL` | Navigate URLs, interact with web page elements |
| `TERMINAL` | Execute shell commands, read output |

### Development Workflow

```bash
npx ogenti validate        # Validate manifest & structure
npx ogenti test            # Run test suite against sandbox
npx ogenti publish         # Bundle and publish to marketplace
```

<br/>

## 📡 API Reference

### REST Endpoints

| Method | Endpoint | Auth | Description |
|:-------|:---------|:-----|:------------|
| `POST` | `/api/auth/register` | — | Create new user account |
| `POST` | `/api/auth/login` | — | Authenticate and receive JWT tokens |
| `GET` | `/api/agents` | — | List marketplace agents (paginated, filterable) |
| `GET` | `/api/agents/:id` | — | Get full agent details |
| `POST` | `/api/execution/start` | 🔒 | Start agent execution session |
| `POST` | `/api/execution/stop` | 🔒 | Stop a running execution |
| `GET` | `/api/execution/sessions` | 🔒 | List user's execution sessions |
| `POST` | `/api/payments/checkout` | 🔒 | Create Stripe checkout session |
| `GET` | `/api/settings` | 🔒 | Get user settings & LLM config |
| `PUT` | `/api/settings` | 🔒 | Update user settings |
| `GET` | `/api/developer/agents` | 🔒 | List developer's published agents |
| `POST` | `/api/developer/upload` | 🔒 | Upload agent bundle to marketplace |

### WebSocket Events

| Event | Direction | Payload |
|:------|:----------|:--------|
| `execution:start` | Server → Client | Session metadata, agent info |
| `execution:log` | Server → Client | Real-time log entry with level & timestamp |
| `execution:screenshot` | Server → Client | Base64 screenshot of agent activity |
| `execution:complete` | Server → Client | Final result, duration, status |
| `execution:error` | Server → Client | Error details, stack trace |
| `agent:status` | Server → Client | Agent online/offline state change |

<br/>

## 🗄️ Database Schema

Core data models managed by Prisma ORM:

| Model | Description |
|:------|:------------|
| **User** | Authentication, profile, Stripe customer ID, roles (`USER` · `DEVELOPER` · `ADMIN`) |
| **Agent** | Marketplace listing — metadata, pricing, bundle path, review status, analytics |
| **Purchase** | Payment records, license keys, platform fees, developer payout tracking |
| **ExecutionSession** | Agent run sessions — prompt, config, result, timing, status |
| **ExecutionLog** | Per-session log entries with level, message, screenshot references |
| **LLMConfig** | Per-user encrypted LLM provider configurations |

<br/>

## 🛠️ Scripts Reference

| Command | Description |
|:--------|:------------|
| `npm run dev` | Start backend + frontend in dev mode |
| `npm run dev:runtime` | Start Python agent runtime |
| `npm run build` | Build backend + frontend for production |
| `npm run build:all` | Build everything including Electron |
| `npm run build:electron` | Package desktop app |
| `npm run db:migrate` | Run Prisma migrations |
| `npm run db:seed` | Seed database with sample data |
| `npm run db:studio` | Open Prisma Studio GUI |
| `npm run lint` | Run linters across all packages |
| `npm run test` | Run test suites |

<br/>

## 📄 License

This software is **proprietary**. See [LICENSE](LICENSE) for full terms.

| Use | Terms |
|:----|:------|
| **Evaluation** | Free 30-day trial for non-commercial use |
| **Commercial** | Requires a commercial license |

For licensing inquiries, contact [hello@ogenti.app](mailto:hello@ogenti.app).

<br/>

## 📬 Contact

| Channel | Link |
|:--------|:-----|
| Website | [ogenti.app](https://ogenti.app) |
| Documentation | [ogenti.app/docs](https://ogenti.app/docs) |
| Email | [hello@ogenti.app](mailto:hello@ogenti.app) |

<br/>

---

<div align="center">

<sub>Built with precision. Powered by AI. Controlled by agents.</sub>

<br/><br/>

**[⬆ Back to top](#-ogenti)**

</div>
