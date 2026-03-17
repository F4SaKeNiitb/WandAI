"""
A2A Protocol FastAPI Routes.
Provides JSON-RPC 2.0 endpoints and AgentCard discovery for each WandAI agent.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from a2a.agent_cards import get_agent_cards
from a2a.models import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    Message,
    TextPart,
)
from a2a.task_manager import A2ATaskManager

router = APIRouter(prefix="/a2a", tags=["a2a"])

# Initialized during app startup (set from main.py)
task_manager: A2ATaskManager | None = None

VALID_AGENTS = {"researcher", "coder", "analyst", "writer", "orchestrator"}


# ---------------------------------------------------------------------------
# AgentCard discovery
# ---------------------------------------------------------------------------

@router.get("/{agent}/.well-known/agent.json")
async def get_agent_card(agent: str, request: Request):
    """Return the AgentCard for a specific WandAI agent."""
    if agent not in VALID_AGENTS:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown agent: {agent}"},
        )

    base_url = str(request.base_url).rstrip("/")
    cards = get_agent_cards(base_url)
    card = cards.get(agent)
    if not card:
        return JSONResponse(status_code=404, content={"error": "Agent card not found"})

    return JSONResponse(content=card.model_dump())


@router.get("/.well-known/agents.json")
async def list_agent_cards(request: Request):
    """List all available AgentCards."""
    base_url = str(request.base_url).rstrip("/")
    cards = get_agent_cards(base_url)
    return JSONResponse(content={name: card.model_dump() for name, card in cards.items()})


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 endpoint
# ---------------------------------------------------------------------------

@router.post("/{agent}")
async def handle_jsonrpc(agent: str, request: Request):
    """Handle A2A JSON-RPC 2.0 requests (tasks/send, tasks/get, tasks/cancel, tasks/sendSubscribe)."""
    if agent not in VALID_AGENTS:
        return JSONResponse(
            status_code=404,
            content={"error": f"Unknown agent: {agent}"},
        )

    body = await request.json()
    rpc_request = JSONRPCRequest(**body)

    if rpc_request.method == "tasks/send":
        return await _handle_tasks_send(rpc_request, agent)
    elif rpc_request.method == "tasks/get":
        return await _handle_tasks_get(rpc_request)
    elif rpc_request.method == "tasks/cancel":
        return await _handle_tasks_cancel(rpc_request)
    elif rpc_request.method == "tasks/sendSubscribe":
        return await _handle_tasks_send_subscribe(rpc_request, agent)
    else:
        return JSONResponse(
            content=JSONRPCResponse(
                id=rpc_request.id,
                error=JSONRPCError(code=-32601, message=f"Method not found: {rpc_request.method}"),
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# RPC method handlers
# ---------------------------------------------------------------------------

async def _handle_tasks_send(rpc: JSONRPCRequest, agent: str) -> JSONResponse:
    """Handle tasks/send — create and execute a task."""
    if not task_manager:
        return _error_response(rpc.id, -32603, "Task manager not initialized")

    params = rpc.params or {}
    message_data = params.get("message", {})
    message = _parse_message(message_data)

    task = await task_manager.create_task(message, agent)
    task = await task_manager.execute_task(task.id, agent)

    return JSONResponse(
        content=JSONRPCResponse(id=rpc.id, result=task.model_dump()).model_dump()
    )


async def _handle_tasks_get(rpc: JSONRPCRequest) -> JSONResponse:
    """Handle tasks/get — retrieve task status."""
    if not task_manager:
        return _error_response(rpc.id, -32603, "Task manager not initialized")

    params = rpc.params or {}
    task_id = params.get("id")
    if not task_id:
        return _error_response(rpc.id, -32602, "Missing required param: id")

    task = await task_manager.get_task(task_id)
    if not task:
        return _error_response(rpc.id, -32602, f"Task not found: {task_id}")

    return JSONResponse(
        content=JSONRPCResponse(id=rpc.id, result=task.model_dump()).model_dump()
    )


async def _handle_tasks_cancel(rpc: JSONRPCRequest) -> JSONResponse:
    """Handle tasks/cancel — cancel a running task."""
    if not task_manager:
        return _error_response(rpc.id, -32603, "Task manager not initialized")

    params = rpc.params or {}
    task_id = params.get("id")
    if not task_id:
        return _error_response(rpc.id, -32602, "Missing required param: id")

    task = await task_manager.cancel_task(task_id)
    if not task:
        return _error_response(rpc.id, -32602, f"Task not found: {task_id}")

    return JSONResponse(
        content=JSONRPCResponse(id=rpc.id, result=task.model_dump()).model_dump()
    )


async def _handle_tasks_send_subscribe(rpc: JSONRPCRequest, agent: str) -> StreamingResponse:
    """Handle tasks/sendSubscribe — create task and stream SSE events."""
    if not task_manager:
        return StreamingResponse(
            content=_sse_error("Task manager not initialized"),
            media_type="text/event-stream",
        )

    params = rpc.params or {}
    message_data = params.get("message", {})
    message = _parse_message(message_data)

    task = await task_manager.create_task(message, agent)

    async def event_generator():
        async for event in task_manager.execute_task_streaming(task.id, agent):
            data = json.dumps(event.model_dump())
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        content=event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_message(data: dict) -> Message:
    """Parse a message dict into a Message model."""
    parts = []
    for part_data in data.get("parts", []):
        part_type = part_data.get("type", "text")
        if part_type == "text":
            parts.append(TextPart(text=part_data.get("text", "")))
        else:
            parts.append(TextPart(text=str(part_data)))

    if not parts:
        # Fall back: treat the whole data as text
        text = data.get("text", str(data))
        parts = [TextPart(text=text)]

    return Message(
        role=data.get("role", "user"),
        parts=parts,
        metadata=data.get("metadata"),
    )


def _error_response(rpc_id, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        content=JSONRPCResponse(
            id=rpc_id,
            error=JSONRPCError(code=code, message=message),
        ).model_dump()
    )


async def _sse_error(message: str):
    yield f"data: {json.dumps({'error': message})}\n\n"
