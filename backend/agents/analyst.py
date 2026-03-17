"""
Analyst Agent
Specialized for data analysis, statistical operations, and chart generation.
"""

from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from agents.base import BaseAgent
from core.state import AgentState, AgentType
from core.state_utils import add_log, add_artifact
from tools.chart_generator import generate_chart as generate_chart_direct
from tools.code_executor import execute_python_code as execute_python_code_direct


class AnalystAgent(BaseAgent):
    """
    Analyst agent specialized for data analysis and visualization.
    Can perform statistical analysis and create charts.
    """
    
    agent_type = AgentType.ANALYST

    async def _execute_code(self, code: str) -> tuple[bool, str, str | None]:
        """Execute code via MCP tool if available, otherwise direct."""
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

    async def _generate_chart(self, **kwargs) -> dict:
        """Generate chart via MCP tool if available, otherwise direct."""
        if self.mcp_manager:
            try:
                result = await self.mcp_manager.call_tool("generate_chart", kwargs)
                if isinstance(result, str):
                    import json as _json
                    result = _json.loads(result)
                if isinstance(result, dict):
                    return result
            except Exception:
                pass
        return await generate_chart_direct(**kwargs)

    system_prompt = """You are a Data Analysis Specialist AI agent. Your job is to analyze data and create insightful visualizations.

Your capabilities:
- Analyze datasets and identify patterns
- Perform statistical calculations
- Create charts and visualizations (line, bar, pie, scatter, etc.)
- Generate data insights and summaries

Guidelines:
1. Always start by understanding the data structure
2. Choose appropriate chart types for the data
3. Include clear titles and labels on charts
4. Highlight key insights in your analysis
5. Use statistical measures where appropriate (mean, median, trends)

CRITICAL DATA INTEGRITY RULES:
- ONLY work with data that was provided by previous steps. NEVER fabricate or simulate data.
- If the data from previous steps is incomplete, contains "DATA_NOT_FOUND", or is insufficient for the requested analysis, report this clearly instead of proceeding with fake data.
- It is better to produce no chart than a chart with fabricated data.

For charts, specify:
- Chart type (line, bar, pie, scatter, area)
- Data to plot
- Title and axis labels
- Any specific formatting preferences"""

    async def execute(
        self,
        state: AgentState,
        step_id: str,
        task_description: str
    ) -> tuple[bool, Any, str | None]:
        """
        Execute an analysis task.
        
        Can perform data analysis and/or create visualizations.
        """
        await self.emit_event("analysis_started", state, {
            "step_id": step_id,
            "task": task_description
        })
        
        # Get context from previous steps
        context = self.get_context_from_state(state)
        
        # Determine if this is a chart request or analysis request
        planning_prompt = ChatPromptTemplate.from_messages([
            ("system", """Analyze what type of data analysis task this is.

Respond in JSON format:
{{
    "task_type": "chart" | "analysis" | "both",
    "chart_config": {{
        "chart_type": "line" | "bar" | "pie" | "scatter" | "area",
        "title": "<chart title>",
        "x_label": "<x axis label>",
        "y_label": "<y axis label>",
        "data_description": "<what data to plot>"
    }},
    "analysis_points": ["<point 1>", "<point 2>"],
    "explanation": "<your plan>"
}}

If not creating a chart, set chart_config to null."""),
            ("user", "Task: {task}\n\nAvailable context:\n{context}")
        ])
        
        try:
            plan_chain = planning_prompt | self.llm | JsonOutputParser()
            plan = await plan_chain.ainvoke({
                "task": task_description,
                "context": context
            })
            
            task_type = plan.get("task_type", "analysis")
            results = {}
            
            # Perform analysis if needed
            if task_type in ["analysis", "both"]:
                add_log(state,
                    self.agent_type,
                    "Performing data analysis...",
                    step_id=step_id
                )
                
                analysis_prompt = ChatPromptTemplate.from_messages([
                    ("system", self.system_prompt),
                    ("user", """Analyze this data and provide insights.

Task: {task}
Context: {context}

Provide:
1. Key findings
2. Statistical observations if applicable
3. Patterns or trends
4. Recommendations or conclusions""")
                ])
                
                analysis_chain = analysis_prompt | self.llm
                analysis_result = await analysis_chain.ainvoke({
                    "task": task_description,
                    "context": context
                })
                self._last_usage = getattr(analysis_result, 'usage_metadata', None)

                results["analysis"] = analysis_result.content
                
                add_artifact(state,
                    name=f"analysis_{step_id}",
                    artifact_type="text",
                    content=analysis_result.content,
                    created_by=self.agent_type,
                    step_id=step_id
                )
            
            # Create chart if needed
            if task_type in ["chart", "both"] and plan.get("chart_config"):
                chart_config = plan["chart_config"]
                
                add_log(state,
                    self.agent_type,
                    f"Generating {chart_config.get('chart_type', 'line')} chart...",
                    step_id=step_id
                )
                
                await self.emit_event("chart_generating", state, {
                    "step_id": step_id,
                    "chart_type": chart_config.get("chart_type")
                })
                
                # Generate data for chart using code execution
                data_gen_prompt = ChatPromptTemplate.from_messages([
                    ("system", """Generate Python code that extracts and formats data for a chart from the provided context.

The code should:
1. Extract REAL data from the provided context (previous step results)
2. Print a JSON object with format:
   {{"labels": [...], "values": [...], "datasets": [{{ "label": "...", "data": [...] }}]}}
3. Return your code in JSON format:
{{
    "code": "<your python code here>",
    "explanation": "<brief explanation>"
}}

CRITICAL RULES:
- ONLY use data that exists in the provided context. NEVER fabricate, simulate, or generate fake data.
- If the context does not contain the numerical data needed for the chart, print "ERROR_MISSING_DATA: [describe what data is needed]" instead.
- Do NOT use random numbers or placeholder values as substitutes for real data.

Available libraries: any pip-installable library (auto-installed if missing). Blocked: os, sys, subprocess, socket."""),
                    ("user", "Create data for: {data_desc}\n\nContext: {context}")
                ])
                
                data_chain = data_gen_prompt | self.llm | JsonOutputParser()
                data_result = await data_chain.ainvoke({
                    "data_desc": chart_config.get('data_description', task_description),
                    "context": context
                })
                
                code = data_result.get("code", "")
                if code:
                    success, output, error = await self._execute_code(code)

                    # Check if code reported missing data
                    if success and output and "ERROR_MISSING_DATA:" in output:
                        add_log(state, self.agent_type,
                            f"Chart data unavailable: {output[:200]}",
                            level="warning", step_id=step_id
                        )
                        results["data_warning"] = output
                        # Skip chart generation — data is missing
                        success = False

                    if success and output:
                        try:
                            import json
                            import re
                            
                            # robustness: try to find json object in output
                            output_str = output.strip()
                            try:
                                chart_data = json.loads(output_str)
                            except json.JSONDecodeError:
                                # Try to find brace-enclosed JSON
                                match = re.search(r'\{.*\}', output_str, re.DOTALL)
                                if match:
                                    chart_data = json.loads(match.group())
                                else:
                                    raise
                            
                            # Generate the chart
                            chart_result = await self._generate_chart(
                                chart_type=chart_config.get("chart_type", "line"),
                                data=chart_data,
                                title=chart_config.get("title", "Chart"),
                                x_label=chart_config.get("x_label", ""),
                                y_label=chart_config.get("y_label", "")
                            )
                            
                            if chart_result.get("success"):
                                add_artifact(state,
                                    name=f"chart_{step_id}",
                                    artifact_type="chart",
                                    content={
                                        "title": chart_config.get("title"),
                                        "type": chart_config.get("chart_type"),
                                        "image_base64": chart_result.get("image_base64"),
                                        "image_path": chart_result.get("image_path")
                                    },
                                    created_by=self.agent_type,
                                    step_id=step_id
                                )
                                
                                results["chart"] = {
                                    "title": chart_config.get("title"),
                                    "type": chart_config.get("chart_type"),
                                    "generated": True
                                }
                                
                                await self.emit_event("chart_completed", state, {
                                    "step_id": step_id,
                                    "chart_title": chart_config.get("title")
                                })
                        except Exception as e:
                            add_log(state,
                                self.agent_type,
                                f"Chart data parsing failed: {str(e)}",
                                level="warning",
                                step_id=step_id
                            )
            
            await self.emit_event("analysis_completed", state, {
                "step_id": step_id,
                "results_types": list(results.keys())
            })
            
            # Return combined results
            if results:
                summary = []
                if "data_warning" in results:
                    summary.append(f"DATA_NOT_FOUND: {results['data_warning']}")
                if "analysis" in results:
                    summary.append(f"Analysis:\n{results['analysis']}")
                if "chart" in results:
                    summary.append(f"Chart created: {results['chart'].get('title', 'Untitled')}")

                return True, "\n\n".join(summary), None

            return False, None, "No analysis or chart could be generated"
            
        except Exception as e:
            return False, None, str(e)
