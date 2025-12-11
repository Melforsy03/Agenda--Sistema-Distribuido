import websockets
import asyncio
import json
import os
import logging
import atexit
import warnings

# Suppress specific websocket warnings
warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*Event loop is closed.*')
warnings.filterwarnings('ignore', category=ResourceWarning, message='.*unclosed.*')

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
        self._cleanup_registered = False
        
        # Register cleanup on exit
        if not self._cleanup_registered:
            atexit.register(self._sync_cleanup)
            self._cleanup_registered = True
        
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
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await asyncio.wait_for(self.listener_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass  # Ignore cancellation and timeout errors
        
        # Close websocket connection
        if self.websocket:
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass  # Ignore errors during close
            finally:
                self.websocket = None
                self.connected = False
                self.logger.info("Disconnected from WebSocket server")
    
    def _sync_cleanup(self):
        """Synchronous cleanup for atexit"""
        if self.websocket or self.listener_task:
            try:
                # Try to get or create an event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_closed():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Run cleanup
                if not loop.is_closed():
                    loop.run_until_complete(self._async_cleanup())
            except Exception:
                pass  # Ignore all errors during cleanup
    
    async def _async_cleanup(self):
        """Async cleanup helper"""
        self.should_stop = True
        self.listening = False
        
        # Cancel listener task
        if self.listener_task and not self.listener_task.done():
            self.listener_task.cancel()
            try:
                await asyncio.wait_for(self.listener_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        
        # Close websocket connection
        if self.websocket:
            try:
                # Set a timeout for closing
                close_task = asyncio.create_task(self.websocket.close())
                await asyncio.wait_for(close_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                # Force close if timeout
                if self.websocket and hasattr(self.websocket, 'transport'):
                    try:
                        self.websocket.transport.close()
                    except:
                        pass
            except Exception:
                pass
            finally:
                self.websocket = None
        
        self.connected = False
        
        # Cancel any remaining tasks in the current event loop
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                pending = [task for task in asyncio.all_tasks(loop) 
                          if not task.done() and task != asyncio.current_task()]
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
        except Exception:
            pass
    
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
                    if self.should_stop:
                        break
                    continue
                except asyncio.CancelledError:
                    # Task was cancelled, exit gracefully
                    self.logger.info("Listen task cancelled")
                    break
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
                    if self.should_stop:
                        break
                    continue
                    
        except asyncio.CancelledError:
            self.logger.info("Listen task cancelled during execution")
        except Exception as e:
            self.logger.error(f"Unexpected error in listen loop: {e}")
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