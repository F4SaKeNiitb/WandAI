"""
Researcher Agent
Specialized for web searches and data retrieval from external sources.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agents.base import BaseAgent
from core.state import AgentState, AgentType
from tools.search import search_web


class ResearcherAgent(BaseAgent):
    """
    Researcher agent specialized for information gathering.
    Uses web search tools to find and retrieve relevant data.
    """
    
    agent_type = AgentType.RESEARCHER
    system_prompt = """You are a Research Specialist AI agent. Your job is to find accurate, up-to-date information from the web.

Your capabilities:
- Search the web for current information
- Retrieve data from news sources, APIs, and databases
- Extract relevant facts and figures
- Cite sources for verification

Guidelines:
1. Always search for the most recent information
2. Prefer authoritative sources (official websites, major news outlets)
3. Extract specific data points, not just general information
4. Include source URLs for verification
5. If information is not found, clearly state that

Output your findings in a structured format."""

    async def execute(
        self,
        state: AgentState,
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute a research task.
        
        Returns structured research findings.
        """
        await self.emit_event("research_started", state, {
            "step_id": step_id,
            "task": task_description
        })
        
        # Get context from previous steps
        context = self.get_context_from_state(state)
        
        # First, determine what to search for
        planning_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a research planning assistant. Given a research task, 
determine the best search queries to find the required information.

Respond in JSON format:
{{
    "queries": ["<search query 1>", "<search query 2>"],
    "reasoning": "<why these queries will help>"
}}

Generate 1-3 focused search queries."""),
            ("user", f"Research task: {task_description}\n\nContext: {context}")
        ])
        
        try:
            # Plan the searches
            planning_chain = planning_prompt | self.llm | JsonOutputParser()
            plan = await planning_chain.ainvoke({})
            queries = plan.get("queries", [task_description])
            
            state.add_log(
                self.agent_type,
                f"Searching with {len(queries)} queries",
                step_id=step_id
            )
            
            # Execute searches
            all_results = []
            for query in queries[:3]:  # Limit to 3 queries
                await self.emit_event("searching", state, {
                    "step_id": step_id,
                    "query": query
                })
                
                results = await search_web(query)
                if results:
                    all_results.extend(results)
            
            if not all_results:
                return False, None, "No search results found"
            
            # Synthesize findings
            synthesis_prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                ("user", """Based on these search results, extract the information needed for the task.

Task: {task}

Search Results:
{results}

Provide a structured summary with:
1. Key findings
2. Relevant data points
3. Source citations""")
            ])
            
            results_text = "\n\n".join([
                f"Source: {r.get('url', 'Unknown')}\nTitle: {r.get('title', '')}\nContent: {r.get('content', '')}"
                for r in all_results[:10]  # Limit results
            ])
            
            synthesis_chain = synthesis_prompt | self.llm
            response = await synthesis_chain.ainvoke({
                "task": task_description,
                "results": results_text
            })
            
            # Store as artifact
            artifact_id = state.add_artifact(
                name=f"research_{step_id}",
                artifact_type="text",
                content=response.content,
                created_by=self.agent_type,
                step_id=step_id
            )
            
            await self.emit_event("research_completed", state, {
                "step_id": step_id,
                "artifact_id": artifact_id,
                "sources_count": len(all_results)
            })
            
            return True, response.content, None
            
        except Exception as e:
            return False, None, str(e)
