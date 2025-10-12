import websockets
import asyncio
import json
import os
import logging

class WebSocketClient:
    def __init__(self):
        self.websocket = None
        self.host = os.getenv('WEBSOCKET_HOST', 'localhost')
        self.port = os.getenv('WEBSOCKET_PORT', '8767')
        self.url = f"ws://{self.host}:{self.port}"
        self.user_id = None
        self.connected = False
        self.message_handlers = {}
        self.logger = logging.getLogger(__name__)
        self.listening = False
        self.listener_task = None
        self.should_stop = False
        
    async def connect(self, user_id):
        """Connect to the WebSocket server"""
        try:
            self.websocket = await websockets.connect(self.url)
            self.user_id = user_id
            
            # Authenticate with the server
            auth_message = {
                "type": "auth",
                "user_id": user_id
            }
            await self.websocket.send(json.dumps(auth_message))
            
            # Wait for authentication response
            response = await self.websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") == "auth_success":
                self.connected = True
                self.logger.info(f"Connected to WebSocket server at {self.url}")
                return True
            else:
                self.logger.error(f"Authentication failed: {response_data}")
                await self.websocket.close()
                self.websocket = None
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to connect to WebSocket server: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the WebSocket server"""
        self.should_stop = True
        self.listening = False
        
        # Cancel listener task if it exists
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except (asyncio.CancelledError, Exception):
                pass  # Ignore cancellation errors
        
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass  # Ignore errors during close
            self.websocket = None
            self.connected = False
            self.logger.info("Disconnected from WebSocket server")
    
    async def send_message(self, message):
        """Send a message to the server"""
        if not self.connected or not self.websocket:
            return False
            
        try:
            await self.websocket.send(json.dumps(message))
            return True
        except Exception:
            return False
    
    async def listen(self):
        """Listen for messages from the server"""
        if not self.connected or not self.websocket:
            return
            
        if self.listening:
            return
            
        self.listening = True
        self.should_stop = False
        self.logger.info("Starting to listen for WebSocket messages")
        
        try:
            while not self.should_stop and self.connected and self.websocket:
                try:
                    # Use wait_for to avoid blocking indefinitely
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    data = json.loads(message)
                    message_type = data.get("type")
                    
                    # Handle ping messages automatically
                    if message_type == "ping":
                        await self.send_message({"type": "pong"})
                        continue
                    
                    # Call registered handlers for this message type
                    if message_type in self.message_handlers:
                        for handler in self.message_handlers[message_type]:
                            try:
                                # Run handler synchronously to avoid task creation issues
                                handler(data)
                            except Exception as e:
                                self.logger.error(f"Error in message handler: {e}")
                    else:
                        self.logger.info(f"Received unhandled message: {data}")
                        
                except asyncio.TimeoutError:
                    # Timeout is expected, continue listening
                    continue
                except json.JSONDecodeError:
                    self.logger.error("Invalid JSON message received")
                except websockets.exceptions.ConnectionClosed:
                    self.logger.info("WebSocket connection closed")
                    self.connected = False
                    break
                except Exception as e:
                    if "Event loop is closed" in str(e):
                        self.connected = False
                        break
                    self.logger.error(f"Error while listening for messages: {e}")
                    continue
                    
        finally:
            self.listening = False
            self.should_stop = True
            self.logger.info("Stopped listening for WebSocket messages")
    
    def register_handler(self, message_type, handler):
        """Register a handler for a specific message type"""
        if message_type not in self.message_handlers:
            self.message_handlers[message_type] = []
        self.message_handlers[message_type].append(handler)
    
    def unregister_handler(self, message_type, handler):
        """Unregister a handler for a specific message type"""
        if message_type in self.message_handlers:
            if handler in self.message_handlers[message_type]:
                self.message_handlers[message_type].remove(handler)
            if not self.message_handlers[message_type]:
                del self.message_handlers[message_type]