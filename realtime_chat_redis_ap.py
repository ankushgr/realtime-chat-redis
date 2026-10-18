import redis.asyncio as redis
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from auth import verify_token

@asynccontextmanager
async def lifespan(app:FastAPI):
    task = asyncio.create_task(redis_listener())
    yield
    task.cancel()
app = FastAPI(lifespan=lifespan)

r = redis.from_url("redis://localhost:6379",socket_connect_timeout=2)

async def redis_listener():
    while True:
        try:
            pubsub = r.pubsub()
            await pubsub.subscribe("chat")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await manager.broadcast(message["data"].decode())
        except Exception as e:
            print("Listener Error:",repr(e))
            await asyncio.sleep(2)



class ConnectionManager:
    def __init__(self):
        self.active_connections : list[WebSocket] = []

    async def connect(self, websocket:WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self,websocket:WebSocket):
        self.active_connections.remove(websocket)
    async def broadcast(self, message:str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket:WebSocket, token:str = Query()):

    try:
        email = verify_token(token)
    except Exception:
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                await r.publish("chat",f"{email}: {data}")

            except redis.ConnectionError:
                await websocket.send_text("Server Error: Chat is Temporarily down")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("Client Disconnected")