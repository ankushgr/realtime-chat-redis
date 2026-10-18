# Realtime Chat with Redis Pub/Sub

A small WebSocket chat server built with FastAPI. The interesting part is that it runs fine across multiple server processes: a message sent to one server shows up for clients connected to any other server.

I built this to understand why a plain WebSocket broadcast breaks the moment you run more than one server, and how Redis pub/sub fixes it.

## The problem

With a single server, broadcasting is easy. The server keeps a list of connected clients and loops over it.

Once you run two servers, each one only knows about its own clients. If Alice is connected to server 1 and Bob to server 2, server 1 can't reach Bob. Its list lives in its own memory.

## How it works

Instead of broadcasting directly, a server publishes every incoming message to a Redis channel. Every server (including the one that received the message) is subscribed to that channel and broadcasts whatever arrives to its own clients.

```
  Alice                                   Bob
    |                                      |
    v                                      v
+----------+                         +----------+
| Server 1 |                         | Server 2 |
| :8000    |                         | :8001    |
+----------+                         +----------+
    |  publish                  subscribe  ^
    |                                      |
    v                                      |
  +------------------------------------------+
  |           Redis  (channel: "chat")       |
  +------------------------------------------+
```

Flow:

1. Alice sends a message over her WebSocket to server 1.
2. Server 1 publishes it to the `chat` channel in Redis.
3. Both servers receive it from the channel through a background listener.
4. Each server sends it to its own connected clients, so Bob gets it from server 2.

## What happens when Redis goes down

I tested this on purpose by stopping the Redis container while the servers were running.

- If someone sends a message while Redis is down, the sender gets an error message over the WebSocket and the connection stays open. It doesn't crash.
- The background listener catches the error, waits a couple of seconds and tries to subscribe again in a loop.
- When Redis comes back, the listeners re-subscribe on their own. No server restart needed.

To check that the listeners are really back, you can ask Redis how many subscribers the channel has:

```
docker exec -it redis redis-cli pubsub numsub chat
```

With two servers running, it should print `2`.

## Tech

- Python, FastAPI, WebSockets
- Redis (pub/sub) through `redis.asyncio`
- JWT authentication on the WebSocket connection
- Docker, only to run Redis locally

## Running it locally

You need Python 3.10 or newer and Docker.

**1. Start Redis**

```
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

I pinned `redis:7-alpine` because the `latest` image kept exiting on startup on my machine.

**2. Install dependencies**

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**3. Start two servers**

Open two terminals and run one command in each:

```
uvicorn main:app --port 8000
uvicorn main:app --port 8001
```

Replace `main` with the name of the Python file if yours is different.

**4. Connect two clients**

The WebSocket endpoint is `/ws` and it expects a JWT in the query string:

```
ws://localhost:8000/ws?token=YOUR_TOKEN
```

The quickest way to try it is the browser console. Open `http://localhost:8000/docs` in one tab and `http://localhost:8001/docs` in another, open the console in each, and paste:

```js
var ws = new WebSocket("ws://localhost:8000/ws?token=YOUR_TOKEN");
ws.onmessage = e => console.log("got:", e.data);
```

Use port 8001 in the second tab. Then send a message from the first tab:

```js
ws.send("hello")
```

Both tabs should print it.

## A note on the secret key

`auth.py` has a placeholder `SECRET_KEY`. Change it to your own random value before using this for anything real. Reading it from an environment variable would be the proper fix, and it's on my list.

## Limitations

- Redis pub/sub doesn't store anything. If a server isn't subscribed at the moment a message is published, it never sees that message, and there's no chat history.
- There are no rooms. Every message goes to every connected client.
- Redis is a single point of failure here. A real setup would use a managed Redis or replicas.

## Ideas for next

- Save messages to a database so new clients can load history
- Chat rooms, so messages only go to people in the same room
- Tests with pytest
- Deploy it somewhere with a live URL
