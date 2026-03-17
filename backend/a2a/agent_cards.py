"""
AgentCard definitions for each WandAI agent.
"""

from a2a.models import AgentCard, AgentSkill, AgentCapabilities


def get_agent_cards(base_url: str = "http://localhost:8000") -> dict[str, AgentCard]:
    """Return AgentCard definitions for all WandAI agents."""
    return {
        "researcher": AgentCard(
            name="WandAI Researcher",
            description="Web research and data gathering agent. Searches the web, retrieves facts, and produces structured research summaries with citations.",
            url=f"{base_url}/a2a/researcher",
            skills=[
                AgentSkill(
                    id="web-search",
                    name="Web Search",
                    description="Search the web for current information on any topic",
                    tags=["search", "research", "web"],
                    examples=["Find the latest revenue figures for Tesla"],
                ),
                AgentSkill(
                    id="news-search",
                    name="News Search",
                    description="Search for recent news articles",
                    tags=["news", "current-events"],
                    examples=["What are the latest AI policy developments?"],
                ),
            ],
            capabilities=AgentCapabilities(streaming=True),
            defaultOutputModes=["text/plain", "application/json"],
        ),
        "coder": AgentCard(
            name="WandAI Coder",
            description="Python code generation and execution agent. Writes, runs, and debugs Python code in a sandboxed environment.",
            url=f"{base_url}/a2a/coder",
            skills=[
                AgentSkill(
                    id="code-execution",
                    name="Code Execution",
                    description="Write and execute Python code for calculations, data processing, and automation",
                    tags=["python", "code", "computation"],
                    examples=["Calculate the compound interest on $10,000 at 5% for 10 years"],
                ),
                AgentSkill(
                    id="data-processing",
                    name="Data Processing",
                    description="Process and transform data using pandas and numpy",
                    tags=["data", "pandas", "numpy"],
                    examples=["Parse this CSV data and compute summary statistics"],
                ),
            ],
            capabilities=AgentCapabilities(streaming=True),
            defaultOutputModes=["text/plain", "application/json"],
        ),
        "analyst": AgentCard(
            name="WandAI Analyst",
            description="Data analysis and visualization agent. Performs statistical analysis and generates charts.",
            url=f"{base_url}/a2a/analyst",
            skills=[
                AgentSkill(
                    id="data-analysis",
                    name="Data Analysis",
                    description="Analyze datasets, identify patterns, and compute statistics",
                    tags=["analysis", "statistics"],
                    examples=["Analyze sales trends from the provided data"],
                ),
                AgentSkill(
                    id="chart-generation",
                    name="Chart Generation",
                    description="Create line, bar, pie, scatter, and area charts",
                    tags=["visualization", "chart", "matplotlib"],
                    examples=["Create a bar chart comparing Q1-Q4 revenue"],
                ),
            ],
            capabilities=AgentCapabilities(streaming=True),
            defaultOutputModes=["text/plain", "image/png"],
        ),
        "writer": AgentCard(
            name="WandAI Writer",
            description="Text generation and summarization agent. Creates reports, summaries, and structured documents.",
            url=f"{base_url}/a2a/writer",
            skills=[
                AgentSkill(
                    id="summarization",
                    name="Summarization",
                    description="Summarize complex information into concise text",
                    tags=["writing", "summarization"],
                    examples=["Summarize these research findings into an executive brief"],
                ),
                AgentSkill(
                    id="report-generation",
                    name="Report Generation",
                    description="Generate structured reports with markdown formatting",
                    tags=["writing", "report", "markdown"],
                    examples=["Write a market analysis report based on this data"],
                ),
            ],
            capabilities=AgentCapabilities(streaming=True),
            defaultOutputModes=["text/plain", "text/markdown"],
        ),
        "orchestrator": AgentCard(
            name="WandAI Orchestrator",
            description="Multi-agent orchestrator that decomposes complex tasks into subtasks, delegates to specialist agents, and synthesizes results.",
            url=f"{base_url}/a2a/orchestrator",
            skills=[
                AgentSkill(
                    id="task-planning",
                    name="Task Planning",
                    description="Decompose complex requests into executable multi-step plans",
                    tags=["planning", "orchestration"],
                    examples=["Research Tesla's financials, analyze the data, and write a report"],
                ),
                AgentSkill(
                    id="multi-agent-coordination",
                    name="Multi-Agent Coordination",
                    description="Coordinate multiple specialist agents to solve complex problems",
                    tags=["coordination", "multi-agent"],
                    examples=["Compare three companies' market performance with charts"],
                ),
            ],
            capabilities=AgentCapabilities(streaming=True),
            defaultOutputModes=["text/plain", "text/markdown", "image/png"],
        ),
    }
