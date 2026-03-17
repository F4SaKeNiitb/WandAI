"""
A2A Client for outbound agent-to-agent communication.
Allows WandAI to discover and delegate tasks to external A2A-compliant agents.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from a2a.models import (
    AgentCard,
    Artifact,
    JSONRPCRequest,
    JSONRPCResponse,
    Message,
    Task,
    TaskStatusUpdateEvent,
    TextPart,
)


class A2AClient:
    """Client for communicating with external A2A-compliant agents."""

    def __init__(self, timeout: float = 120.0):
        self.timeout = timeout
        self._agent_cards: dict[str, AgentCard] = {}

    async def discover(self, base_url: str) -> AgentCard:
        """Discover an external agent by fetching its AgentCard.

        Args:
            base_url: The agent's base URL (e.g. http://host:port/a2a/agent).

        Returns:
            The AgentCard for the discovered agent.
        """
        card_url = f"{base_url.rstrip('/')}/.well-known/agent.json"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(card_url)
            response.raise_for_status()
            card = AgentCard(**response.json())
            self._agent_cards[base_url] = card
            return card

    async def send_task(self, agent_url: str, message: str) -> Task:
        """Send a task to an external A2A agent and wait for completion.

        Args:
            agent_url: The agent's JSON-RPC endpoint URL.
            message: The user message text to send.

        Returns:
            The completed Task with results.
        """
        rpc_request = JSONRPCRequest(
            id="1",
            method="tasks/send",
            params={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                }
            },
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                agent_url,
                json=rpc_request.model_dump(),
            )
            response.raise_for_status()
            rpc_response = JSONRPCResponse(**response.json())

            if rpc_response.error:
                raise RuntimeError(
                    f"A2A error {rpc_response.error.code}: {rpc_response.error.message}"
                )

            return Task(**rpc_response.result)

    async def send_task_streaming(
        self, agent_url: str, message: str
    ) -> AsyncIterator[dict]:
        """Send a task and stream SSE events.

        Args:
            agent_url: The agent's JSON-RPC endpoint URL.
            message: The user message text to send.

        Yields:
            Parsed SSE event dictionaries.
        """
        rpc_request = JSONRPCRequest(
            id="1",
            method="tasks/sendSubscribe",
            params={
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                }
            },
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                agent_url,
                json=rpc_request.model_dump(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue

    async def get_task(self, agent_url: str, task_id: str) -> Task:
        """Get the status of a task from an external agent.

        Args:
            agent_url: The agent's JSON-RPC endpoint URL.
            task_id: The task ID to query.

        Returns:
            The Task with current status.
        """
        rpc_request = JSONRPCRequest(
            id="1",
            method="tasks/get",
            params={"id": task_id},
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                agent_url,
                json=rpc_request.model_dump(),
            )
            response.raise_for_status()
            rpc_response = JSONRPCResponse(**response.json())

            if rpc_response.error:
                raise RuntimeError(
                    f"A2A error {rpc_response.error.code}: {rpc_response.error.message}"
                )

            return Task(**rpc_response.result)

    def get_cached_card(self, base_url: str) -> AgentCard | None:
        """Return a previously discovered AgentCard from cache."""
        return self._agent_cards.get(base_url)
