# 🪄 WandAI - Multi-Agent AI Orchestration System

## 🏗️ Design Decisions

The system was designed with a modular, agentic architecture to handle complex, multi-step requests.

### 1. Orchestration via LangGraph
Instead of a simple linear chain, we used **LangGraph** to model the workflow as a stateful graph. This allows for:
- **Cyclic Execution**: Agents can loop back (e.g., retrying failed steps).
- **Dynamic Routing**: The Orchestrator decides execution order based on dependencies.
- **Human-in-the-Loop**: The graph can pause for user approval or clarification.

### 2. The "Blackboard" State Pattern
We use a centralized `AgentState` object that all agents read from and write to. This avoids passing complex outputs directly between agents and provides a single source of truth for the Frontend to render.
- **Artifacts**: Files (charts, scripts) are stored in a unified ID-based dictionary.
- **Logs**: A shared append-only log allows real-time visibility into every agent's thought process.

### 3. Separation of Planning & Execution
- **Orchestrator Agent**: Acts as the project manager. It does *not* execute tasks but breaks them down into a `Plan` (list of steps with dependencies).
- **Specialized Agents**: (Researcher, Coder, Analyst) are laser-focused on execution. They don't worry about the bigger picture, just their assigned `step_id`.

### 4. Hybrid Frontend/Backend
- **Backend (FastAPI)**: Handles the heavy lifting of agent orchestration and LLM interaction. Async Python is ideal for I/O bound LLM calls.
- **Frontend (React + Vite)**: Provides a responsive, "Mission Control" style interface. We chose **WebSocket** for real-time updates so the user isn't staring at a spinner for 2 minutes.

---

## ⚖️ Trade-offs (24h Constraint)

Due to the limited development window, several trade-offs were made:

- **In-Memory Persistence**: We use `MemorySaver` for graph state.
  - *Consequence*: If the backend restarts, all session history and artifacts are lost.
  - *Ideal Approach*: A Postgres/Redis backed checkpointer for long-term persistence.
- **Sandboxed Execution**: Code execution uses a lightweight `exec()` restriction.
  - *Consequence*: It blocks dangerous imports (os, sys) but isn't as secure as a true containerized sandbox (e.g., Docker-in-Docker or Firecracker).
- **No User Authentication**: The system assumes a single tenant (or trusted environment).
  - *Consequence*: No multi-user separation or saved user profiles.
- **Generic System Prompts**: Agents use robust but static system prompts.
  - *Consequence*: They work well for general tasks/coding but aren't fine-tuned for niche domains.

---

## 🚀 How to Run & Test

### Backend Setup

1. **Navigate to backend**:
   ```bash
   cd backend
   ```
2. **Install Dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Configure Environment**:
   - Copy `.env.example` to `.env`.
   - Add your `OPENAI_API_KEY` (or Gemini/Anthropic keys if supported).
   - Add `TAVILY_API_KEY` for web search capabilities.
4. **Run Server**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   *Note: Restart this process if you modify backend code.*

### Frontend Setup

1. **Navigate to frontend**:
   ```bash
   cd frontend
   ```
2. **Install Dependencies**:
   ```bash
   npm install
   ```
3. **Run Development Server**:
   ```bash
   npm run dev
   ```
4. **Access UI**:
   - Open [http://localhost:5173](http://localhost:5173) in your browser.

### Testing the System

1. **Basic Test**: Input "Calculate the 10th Fibonacci number" to test the Coder agent.
2. **Research Test**: Input "Who won the Super Bowl in 2024?" to test the Researcher (requires Tavily key).
3. **Graph Test**: Input "Plot a sine wave" to test Analyst + Chart generation.
4. **Refinement Test**: After a result is generated, use the chat box to ask "Change the color to red" to test the refinement loop.
