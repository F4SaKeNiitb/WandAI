"""
Coder Agent
Specialized for Python code generation and execution.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agents.base import BaseAgent
from core.state import AgentState, AgentType
from core.state_utils import get_state_attr, get_artifact_attr, add_log, add_artifact
from tools.code_executor import execute_python_code as execute_python_code_direct


class CoderAgent(BaseAgent):
    """
    Coder agent specialized for Python code execution.
    Can write and execute code with error correction.
    """
    
    agent_type = AgentType.CODER

    async def _execute_code(self, code: str) -> tuple[bool, str, str | None]:
        """Execute code via MCP tool if available, otherwise use direct import."""
        if self.mcp_manager:
            try:
                result = await self.mcp_manager.call_tool("execute_python", {"code": code})
                if isinstance(result, str):
                    import json as _json
                    result = _json.loads(result)
                if isinstance(result, dict):
                    return result.get("success", False), result.get("output", ""), result.get("error")
            except Exception:
                pass
        return await execute_python_code_direct(code)

    system_prompt = """You are a Python Coding Specialist AI agent. Your job is to write and execute Python code to solve computational tasks.

Your capabilities:
- Write clean, efficient Python code
- Perform calculations and data processing
- Work with pandas DataFrames
- Create data transformations
- Handle errors gracefully

Guidelines:
1. Write complete, executable Python code
2. Include print statements to show results
3. Handle potential errors (try/except)
4. Keep code concise and focused
5. Comment complex logic

IMPORTANT:
- Your code runs in a sandboxed environment
- Available libraries: pandas, numpy, json, math, datetime, re, collections
- Do NOT use: os, subprocess, sys, or file I/O
- All output must be via print() statements

CRITICAL DATA INTEGRITY RULES:
- NEVER fabricate, simulate, or generate fake/dummy/sample data to substitute for missing real data.
- If the context from previous steps does not contain the data you need, print a clear error message starting with "ERROR_MISSING_DATA:" explaining exactly what data is missing.
- You may ONLY use hardcoded data if it comes directly from the context/previous step results.
- If previous step results contain "DATA_NOT_FOUND", do NOT proceed with made-up data. Instead, report the error.
- Creating synthetic data is ONLY acceptable when the user explicitly asks for simulations, demos, or example data.

Output your code in a properly formatted code block."""

    async def execute(
        self,
        state: AgentState,
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute a coding task.
        
        Generates Python code, executes it, and returns the result.
        """
        await self.emit_event("coding_started", state, {
            "step_id": step_id,
            "task": task_description
        })
        
        # Get context from previous steps
        context = self.get_context_from_state(state)
        
        # Extract any data from artifacts that might be needed
        data_context = ""
        artifacts = get_state_attr(state, 'artifacts', {})
        for artifact_id, artifact in artifacts.items():
            a_type = get_artifact_attr(artifact, 'type', 'text')
            if a_type == "data":
                a_name = get_artifact_attr(artifact, 'name', artifact_id)
                a_content = get_artifact_attr(artifact, 'content', '')
                data_context += f"\nAvailable data '{a_name}':\n{a_content}\n"
        
        # Generate the code
        code_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("user", """Write Python code to accomplish this task.

Task: {task}

Previous context:
{context}

{data_context}

IMPORTANT:
1. Write complete, executable code
2. Use print() to output results
3. Only use allowed libraries
4. If the previous context does NOT contain the actual data needed, print "ERROR_MISSING_DATA: [describe what data is missing]" instead of making up data
5. NEVER simulate, fabricate, or generate dummy data as a substitute for real data
6. You may ONLY use data values that appear explicitly in the "Previous context" above
7. Return your code in JSON format:
{{
    "code": "<your python code here>",
    "explanation": "<brief explanation of what the code does>"
}}""")
        ])
        
        try:
            import json as _json
            raw_response = await (code_prompt | self.llm).ainvoke({
                "task": task_description,
                "context": context,
                "data_context": data_context or "No additional data available."
            })
            self._last_usage = getattr(raw_response, 'usage_metadata', None)
            content = raw_response.content
            try:
                result = _json.loads(content)
            except _json.JSONDecodeError:
                import re
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    result = _json.loads(match.group())
                else:
                    return False, None, "Failed to parse LLM response as JSON"
            
            code = result.get("code", "")
            if not code:
                return False, None, "No code generated"
            
            add_log(state, self.agent_type,
                f"Generated code ({len(code)} chars), executing...",
                step_id=step_id
            )
            
            await self.emit_event("code_executing", state, {
                "step_id": step_id,
                "code_preview": code[:200] + "..." if len(code) > 200 else code
            })
            
            # Execute the code
            success, output, error = await self._execute_code(code)
            
            if success:
                # Check if the code itself reported missing data
                if output and "ERROR_MISSING_DATA:" in output:
                    add_log(state, self.agent_type,
                        f"Code reported missing data: {output[:200]}",
                        level="warning", step_id=step_id
                    )
                    return False, None, f"Missing data required for this step: {output}"

                # Store code and output as artifacts
                add_artifact(state,
                    name=f"code_{step_id}",
                    artifact_type="code",
                    content={
                        "code": code,
                        "output": output,
                        "explanation": result.get("explanation", "")
                    },
                    created_by=self.agent_type,
                    step_id=step_id
                )
                
                await self.emit_event("code_completed", state, {
                    "step_id": step_id,
                    "output_preview": output[:200] if output else "No output"
                })
                
                return True, output, None
            else:
                # Try to fix the code
                add_log(state,
                    self.agent_type,
                    f"Code execution failed: {error}",
                    level="warning",
                    step_id=step_id
                )
                
                fix_prompt = ChatPromptTemplate.from_messages([
                    ("system", self.system_prompt),
                    ("user", """The following code failed with an error. Please fix it.

Original code:
```python
{code}
```

Error:
{error}

Return the fixed code in JSON format:
{{
    "code": "<fixed python code>",
    "fix_explanation": "<what you fixed>"
}}""")
                ])
                
                fix_chain = fix_prompt | self.llm | JsonOutputParser()
                fix_result = await fix_chain.ainvoke({
                    "code": code,
                    "error": error
                })
                
                fixed_code = fix_result.get("code", "")
                if fixed_code:
                    add_log(state,
                        self.agent_type,
                        "Attempting with fixed code...",
                        step_id=step_id
                    )
                    
                    success2, output2, error2 = await self._execute_code(fixed_code)
                    
                    if success2:
                        add_artifact(state,
                            name=f"code_{step_id}",
                            artifact_type="code",
                            content={
                                "code": fixed_code,
                                "output": output2,
                                "original_error": error,
                                "fix": fix_result.get("fix_explanation", "")
                            },
                            created_by=self.agent_type,
                            step_id=step_id
                        )
                        
                        await self.emit_event("code_completed", state, {
                            "step_id": step_id,
                            "output_preview": output2[:200] if output2 else "No output",
                            "was_fixed": True
                        })
                        
                        return True, output2, None
                    
                    return False, None, f"Code fix failed: {error2}"
                
                return False, None, error
                
        except Exception as e:
            # Check for ImportError and try to auto-install
            import re
            error_str = str(e)
            
            # Match: "No module named 'xyz'"
            missing_module = None
            match = re.search(r"No module named '([^']+)'", error_str)
            if match:
                missing_module = match.group(1).split('.')[0]  # Get root package
            
            if missing_module:
                logger.info(f"🔍 [{self.agent_type}] Detected missing module: {missing_module}")
                add_log(state,
                    self.agent_type,
                    f"Missing module '{missing_module}', attempting to install...",
                    level="warning",
                    step_id=step_id
                )
                
                from tools.dependency_manager import install_package
                success_inst, msg_inst = install_package(missing_module)
                
                if success_inst:
                     add_log(state,
                        self.agent_type,
                        f"Installed '{missing_module}', retrying execution...",
                        step_id=step_id
                    )
                     # Retry execution immediately
                     success3, output3, error3 = await self._execute_code(code)
                     if success3:
                        add_artifact(state,
                            name=f"code_{step_id}",
                            artifact_type="code",
                            content={
                                "code": code,
                                "output": output3,
                                "explanation": result.get("explanation", "") + f" (Auto-installed {missing_module})"
                            },
                            created_by=self.agent_type,
                            step_id=step_id
                        )
                        await self.emit_event("code_completed", state, {
                            "step_id": step_id,
                            "output_preview": output3[:200] if output3 else "No output",
                            "was_fixed": True
                        })
                        return True, output3, None
                     else:
                        error = f"Execution failed even after installing {missing_module}: {error3}"
                else:
                    add_log(state,
                        self.agent_type,
                        f"Failed to install '{missing_module}': {msg_inst}",
                        level="error",
                        step_id=step_id
                    )
            
            return False, None, str(error or e)
