"""
WebSocket Handler
Real-time communication for progress updates.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json

from core.logging import ws_logger as logger, log_websocket_event

router = APIRouter(tags=["websocket"])

# Connection manager for WebSocket clients
class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts events.
    """
    
    def __init__(self):
        # Map session_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # All connections (for broadcast)
        self.all_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket, session_id: str = None):
        """Accept a WebSocket connection."""
        await websocket.accept()
        self.all_connections.add(websocket)
        
        if session_id:
            if session_id not in self.active_connections:
                self.active_connections[session_id] = set()
            self.active_connections[session_id].add(websocket)
            logger.info(f"🔌 Client connected to session: {session_id[:8]}...")
        else:
            logger.info(f"🔌 Client connected (global)")
    
    def disconnect(self, websocket: WebSocket, session_id: str = None):
        """Remove a WebSocket connection."""
        self.all_connections.discard(websocket)
        
        if session_id and session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
            logger.info(f"🔌 Client disconnected from session: {session_id[:8]}...")
        else:
            logger.debug(f"🔌 Client disconnected (global)")
    
    async def send_to_session(self, session_id: str, message: dict):
        """Send a message to all connections for a session."""
        if session_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            
            # Clean up disconnected
            for ws in disconnected:
                self.active_connections[session_id].discard(ws)
    
    async def broadcast(self, message: dict):
        """Broadcast a message to all connections."""
        disconnected = set()
        for connection in self.all_connections:
            try:
                await connection.send_json(message)
            except:
                disconnected.add(connection)
        
        # Clean up disconnected
        for ws in disconnected:
            self.all_connections.discard(ws)


# Global connection manager
manager = ConnectionManager()


async def emit_event(event: dict):
    """
    Event callback for the workflow manager.
    Sends events to appropriate WebSocket clients.
    """
    session_id = event.get("session_id")
    event_type = event.get("type", "unknown")
    
    # Log the event (except keepalives)
    if event_type not in ["keepalive", "pong"]:
        log_websocket_event(event_type, session_id or "broadcast", event)
    
    if session_id:
        await manager.send_to_session(session_id, event)
    else:
        await manager.broadcast(event)


@router.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """
    Global WebSocket endpoint for receiving all events.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # Handle ping/pong for keepalive
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "subscribe":
                    # Subscribe to a specific session
                    session_id = message.get("session_id")
                    if session_id:
                        if session_id not in manager.active_connections:
                            manager.active_connections[session_id] = set()
                        manager.active_connections[session_id].add(websocket)
                        await websocket.send_json({
                            "type": "subscribed",
                            "session_id": session_id
                        })
                        
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


@router.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    """
    Session-specific WebSocket endpoint.
    Receives events only for the specified session.
    """
    await manager.connect(websocket, session_id)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to session. You will receive real-time updates."
        })
        
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "keepalive"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        manager.disconnect(websocket, session_id)


def get_event_callback():
    """
    Returns the event callback function for the workflow manager.
    """
    return emit_event
