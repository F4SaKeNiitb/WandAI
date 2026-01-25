# 🪄 WandAI - Multi-Agent AI Orchestration System

A powerful system that accepts high-level business requests in plain language, uses multiple specialized AI agents to break down tasks, execute subtasks, and return structured results with real-time visibility.

## ✨ Features

- **Intelligent Planning**: Automatically decomposes complex requests into actionable steps
- **Specialized Agents**: 
  - 🔍 **Researcher** - Web searches and data retrieval
  - 💻 **Coder** - Python code execution with self-correction
  - 📊 **Analyst** - Data analysis and chart generation
  - ✍️ **Writer** - Summarization and report formatting
- **Real-time Updates**: WebSocket-based progress streaming
- **Ambiguity Handling**: Asks clarifying questions for vague requests
- **Human-in-the-Loop**: Optional plan approval before execution

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────────────────────────────┐
│    Frontend     │────▶│              Backend                 │
│  (React/Vite)   │◀────│           (FastAPI)                  │
└─────────────────┘ WS  └──────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   Orchestrator  │ ◀── The Hub
                    │   (LangGraph)   │
                    └────────┬────────┘
                             │
           ┌─────────┬───────┼───────┬─────────┐
           ▼         ▼       ▼       ▼         ▼
       Researcher  Coder  Analyst  Writer   [Tools]
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- OpenAI API key (or compatible LLM provider)
- Tavily API key (optional, for web search)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your API keys

# Run the server
uvicorn main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The application will be available at:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/execute` | Submit a new business request |
| POST | `/api/clarify` | Provide clarification answers |
| POST | `/api/approve` | Approve or modify execution plan |
| GET | `/api/status/{session_id}` | Get session status |
| GET | `/api/sessions` | List all active sessions |
| WS | `/ws/{session_id}` | Real-time updates for a session |

## 🔧 Configuration

Edit `backend/.env`:

```env
# LLM Provider
OPENAI_API_KEY=your_key_here

# Search API (optional)
TAVILY_API_KEY=your_key_here

# Agent Settings
MAX_RETRIES=3
STEP_TIMEOUT_SECONDS=60
CLARITY_THRESHOLD=8
```

## 📝 Example Requests

Try these example requests:

1. **Data Analysis**: "Get Tesla's stock price for the last week and plot it"
2. **Calculation**: "Calculate compound interest on $10,000 at 5% for 10 years"
3. **Research**: "What are the top AI trends in 2024?"
4. **Code Generation**: "Write a Python script to analyze CSV data"

## 🏛️ Project Structure

```
WandAI/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Configuration management
│   ├── core/
│   │   ├── state.py         # Shared state schema
│   │   ├── orchestrator.py  # Main orchestrator
│   │   └── graph.py         # LangGraph workflow
│   ├── agents/
│   │   ├── base.py          # Base agent class
│   │   ├── researcher.py    # Research agent
│   │   ├── coder.py         # Code execution agent
│   │   ├── analyst.py       # Analysis agent
│   │   └── writer.py        # Writing agent
│   ├── tools/
│   │   ├── search.py        # Web search tool
│   │   ├── code_executor.py # Sandboxed Python executor
│   │   └── chart_generator.py
│   └── api/
│       ├── routes.py        # REST endpoints
│       └── websocket.py     # WebSocket handlers
│
└── frontend/
    ├── index.html
    ├── package.json
    └── src/
        ├── App.jsx          # Main application
        ├── App.css          # Styles
        ├── hooks/
        │   └── useWebSocket.js
        └── components/
            ├── RequestInput.jsx
            ├── AgentStatusPanel.jsx
            ├── PlanViewer.jsx
            ├── ResultDisplay.jsx
            ├── ClarificationModal.jsx
            └── LogsPanel.jsx
```

## 🛡️ Safety Features

- Sandboxed code execution with restricted imports
- Timeout enforcement for all agent operations  
- Retry logic with self-correction
- Error feedback loops for automatic recovery

## 📄 License

MIT License
