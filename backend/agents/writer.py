"""
Writer Agent
Specialized for text summarization, formatting, and report generation.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate

from agents.base import BaseAgent
from core.state import AgentState, AgentType
from core.state_utils import get_state_attr, get_artifact_attr, add_log, add_artifact


class WriterAgent(BaseAgent):
    """
    Writer agent specialized for text generation and formatting.
    Creates summaries, reports, and well-formatted outputs.
    """
    
    agent_type = AgentType.WRITER
    system_prompt = """You are a Professional Writer AI agent. Your job is to create clear, well-structured written content.

Your capabilities:
- Summarize complex information concisely
- Create structured reports and documents
- Format content for readability
- Adapt tone for different audiences
- Highlight key points and insights

Guidelines:
1. Use clear, professional language
2. Structure content with headers and bullet points
3. Lead with the most important information
4. Keep sentences concise but informative
5. Use markdown formatting for better readability

Output formats you can create:
- Executive summaries
- Detailed reports
- Bullet-point lists
- Q&A format
- Narrative explanations"""

    async def execute(
        self,
        state: AgentState,
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute a writing task.
        
        Creates formatted text content based on available information.
        """
        await self.emit_event("writing_started", state, {
            "step_id": step_id,
            "task": task_description
        })
        
        # Get context from previous steps
        context = self.get_context_from_state(state)
        
        # Collect all relevant artifacts for summarization
        artifacts_content = []
        artifacts = get_state_attr(state, 'artifacts', {})
        for artifact_id, artifact in artifacts.items():
            a_type = get_artifact_attr(artifact, 'type', 'text')
            a_name = get_artifact_attr(artifact, 'name', artifact_id)
            a_content = get_artifact_attr(artifact, 'content', '')
            if a_type in ["text", "data"]:
                artifacts_content.append({
                    "name": a_name,
                    "type": a_type,
                    "content": str(a_content)[:2000]
                })
            elif a_type == "code":
                if isinstance(a_content, dict):
                    artifacts_content.append({
                        "name": a_name,
                        "type": "code_output",
                        "content": a_content.get("output", "")[:1000]
                    })
            elif a_type == "chart":
                if isinstance(a_content, dict):
                    artifacts_content.append({
                        "name": a_name,
                        "type": "chart",
                        "content": f"Chart titled: {a_content.get('title', 'Untitled')}"
                    })
        
        # Determine the writing style/format needed
        writing_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("user", """Create written content for this task.

Task: {task}

Original user request: {original_request}

Context and data from previous steps:
{context}

Artifacts available:
{artifacts}

Instructions:
1. Create well-structured content that addresses the task
2. Use markdown formatting (headers, bullets, bold for emphasis)
3. Include key insights and important numbers
4. Reference any charts or visualizations created
5. Keep the tone professional but accessible
6. CRITICAL: If any of the step results or artifacts contain "DATA_NOT_FOUND" or "ERROR_MISSING_DATA", you MUST clearly inform the reader that the requested data could not be retrieved. NEVER fill in made-up numbers to replace missing data.""")
        ])
        
        try:
            # Format artifacts for the prompt
            artifacts_text = "\n\n".join([
                f"**{a['name']}** ({a['type']}):\n{a['content']}"
                for a in artifacts_content
            ]) if artifacts_content else "No artifacts available."
            
            add_log(state, self.agent_type,
                f"Writing content based on {len(artifacts_content)} artifacts",
                step_id=step_id
            )

            chain = writing_prompt | self.llm
            result = await chain.ainvoke({
                "task": task_description,
                "original_request": get_state_attr(state, 'user_request', ''),
                "context": context,
                "artifacts": artifacts_text
            })
            self._last_usage = getattr(result, 'usage_metadata', None)

            written_content = result.content
            
            # Store as artifact
            add_artifact(state,
                name=f"document_{step_id}",
                artifact_type="text",
                content=written_content,
                created_by=self.agent_type,
                step_id=step_id
            )
            
            await self.emit_event("writing_completed", state, {
                "step_id": step_id,
                "content_length": len(written_content)
            })
            
            return True, written_content, None
            
        except Exception as e:
            return False, None, str(e)
