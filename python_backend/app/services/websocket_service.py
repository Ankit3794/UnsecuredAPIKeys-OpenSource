from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
import asyncio
import json
import structlog
from datetime import datetime

logger = structlog.get_logger()


class WebSocketManager:
    """WebSocket manager for real-time updates, replacing C# SignalR Hub"""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_info: Dict[WebSocket, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        
        # Get client info
        client_info = {
            "connected_at": datetime.utcnow(),
            "ip_address": websocket.client.host if websocket.client else "unknown",
            "user_agent": websocket.headers.get("user-agent", "unknown")
        }
        self.connection_info[websocket] = client_info
        
        logger.info("WebSocket client connected", 
                   ip=client_info["ip_address"], 
                   user_agent=client_info["user_agent"],
                   total_connections=len(self.active_connections))
        
        try:
            # Send initial data
            await self._send_initial_data(websocket)
            
            # Handle incoming messages
            while True:
                data = await websocket.receive_text()
                await self._handle_message(websocket, data)
                
        except WebSocketDisconnect:
            await self.disconnect(websocket)
        except Exception as e:
            logger.error("WebSocket error", error=str(e))
            await self.disconnect(websocket)
    
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        if websocket in self.connection_info:
            client_info = self.connection_info.pop(websocket)
            logger.info("WebSocket client disconnected", 
                       ip=client_info.get("ip_address"),
                       total_connections=len(self.active_connections))
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.warning("Failed to send message to client", error=str(e))
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            await self.disconnect(connection)
    
    async def send_to_client(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to specific client"""
        try:
            message_str = json.dumps(message)
            await websocket.send_text(message_str)
        except Exception as e:
            logger.warning("Failed to send message to specific client", error=str(e))
            await self.disconnect(websocket)
    
    async def _send_initial_data(self, websocket: WebSocket):
        """Send initial data to newly connected client"""
        # Send active user count
        await self.send_to_client(websocket, {
            "type": "active_user_count",
            "data": {"count": len(self.active_connections)}
        })
        
        # Send any other initial data as needed
        await self.send_to_client(websocket, {
            "type": "connection_established",
            "data": {"timestamp": datetime.utcnow().isoformat()}
        })
    
    async def _handle_message(self, websocket: WebSocket, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "ping":
                # Respond to ping with pong
                await self.send_to_client(websocket, {
                    "type": "pong",
                    "data": {"timestamp": datetime.utcnow().isoformat()}
                })
            elif message_type == "get_active_count":
                # Send current active user count
                await self.send_to_client(websocket, {
                    "type": "active_user_count",
                    "data": {"count": len(self.active_connections)}
                })
            else:
                logger.debug("Received unknown message type", type=message_type)
                
        except json.JSONDecodeError:
            logger.warning("Received invalid JSON message", message=message)
        except Exception as e:
            logger.error("Error handling WebSocket message", error=str(e))
    
    async def notify_stats_update(self, stats: Dict[str, Any]):
        """Notify all clients of stats update"""
        await self.broadcast({
            "type": "stats_updated",
            "data": stats
        })
    
    async def notify_key_displayed(self, key_info: Dict[str, Any]):
        """Notify all clients when a key is displayed"""
        await self.broadcast({
            "type": "key_displayed", 
            "data": key_info
        })
    
    async def notify_active_users_changed(self):
        """Notify all clients of active user count change"""
        await self.broadcast({
            "type": "active_user_count",
            "data": {"count": len(self.active_connections)}
        })