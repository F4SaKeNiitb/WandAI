"""
Generic Agent
A flexible agent implementation that can be configured with a custom identity and system prompt.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from agents.base import BaseAgent
from core.state import AgentState

class GenericAgent(BaseAgent):
    """
    A generic agent that operates based on a custom name and system prompt.
    """
    
    def __init__(self, name: str, system_prompt: str, event_callback=None):
        """
        Initialize the custom agent.
        
        Args:
            name: The internal ID/name of the agent (e.g., 'social_media_manager')
            system_prompt: The instructions defining the agent's behavior
            event_callback: Async callback for events
        """
        self.custom_name = name
        # Initialize generic base
        super().__init__(event_callback)
        # Override the agent_type and prompt AFTER init
        # We use the custom name as the agent_type string
        self.agent_type = name 
        self.system_prompt = system_prompt
        
    async def execute(
        self,
        state: AgentState,
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute the task using the custom system prompt.
        """
        try:
            context = self.get_context_from_state(state)
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                ("user", """Task: {task}
                
Context:
{context}

Execute the task and provide the result.""")
            ])
            
            chain = prompt | self.llm | StrOutputParser()
            
            response = await chain.ainvoke({
                "task": task_description,
                "context": context
            })
            
            return True, response, None
            
        except Exception as e:
            return False, None, str(e)
