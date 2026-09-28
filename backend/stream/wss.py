import json
import urllib.parse
import websockets
import aiohttp
import asyncio
import requests
import threading
import time
import datetime
import logging

from state import app_state

logger = logging.getLogger(__name__)

data_global: dict = None
driver_global: dict = None
last_driver_received: datetime.datetime = None

current_session_path = ""
_ws: websockets.WebSocketClientProtocol = None
_loop: asyncio.AbstractEventLoop = None

SUBS_TITLE = ["TimingData", "TimingStats", "TimingAppData", "CarData.z", "Position.z", "WeatherData", "TrackStatus", "ExtrapolatedClock", "RaceControlMessages", "TeamRadio", "LapCount", "SessionInfo"]


async def restart_wss():

    global _ws, data_global, driver_global, last_driver_received

    global _ws
    logger.info("Restarting WebSocket connection...")
    
    data_global = None 
    driver_global = None
    last_driver_received = None

    if _ws:
        await _ws.close()
        _ws = None

async def _get_current_session_path() -> str:

    try:
        url = "https://livetiming.formula1.com/static/SessionInfo.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as res:
                if res.status == 200:
                    raw = await res.read()
                    data = json.loads(raw.decode('utf-8-sig'))
                    return data.get('Path', '')
    except Exception as e:
        logger.error(f"Error fetching current session path: {e}")

    return ""

async def monitor_session():
    """Monitor for session changes and trigger reconnection."""

    global current_session_path

    while True:
        await asyncio.sleep(60)
        try:
            active_path = await _get_current_session_path()

            app_state.last_path_time = datetime.datetime.now()
            if active_path:
                app_state.current_session = active_path

            if not active_path or not current_session_path:
                continue

            data_session_path = data_global.get('SessionInfo', {}).get('Path') if data_global else None

            if active_path != current_session_path:
                logger.info(f"Session path changed from {current_session_path} to {active_path}")
                current_session_path = active_path
                await restart_wss()
            elif data_session_path and data_session_path != active_path:
                logger.warning(f"Data session path {data_session_path} does not match active session path {active_path}, restarting WebSocket")
                current_session_path = active_path
                await restart_wss()

        except Exception as e:
            logger.error(f"Error monitoring session: {e}")

async def _negotiate(session: aiohttp, hub: str) -> tuple[str, str]:
    """Negotiate a SignalR connection, return (token, cookie)."""

    url = f'https://livetiming.formula1.com/signalr/negotiate?connectionData={hub}&clientProtocol=1.5'

    async with session.get(url) as res:
    
        if res.status != 200:
            text = await res.text()
            raise Exception(f"Failed to negotiate: {res.status} {text}")

        res_content: dict = await res.json()
        token = res_content.get('ConnectionToken')
        cookie = res.headers.get('Set-Cookie')

    return token, cookie

async def connect_wss():

    global data_global, driver_global, last_driver_received, _ws
    
    hub = urllib.parse.quote(json.dumps([{"name": "Streaming"}]))

    while True:

        try: 
            async with aiohttp.ClientSession() as session:
                token, cookie = await _negotiate(session, hub)
            
            endcodedToken = urllib.parse.quote(token)
            url = f'wss://livetiming.formula1.com/signalr/connect?clientProtocol=1.5&transport=webSockets&connectionToken={endcodedToken}&connectionData={hub}'

            headers = {
                "User-Agent": "BestHTTP",
                "Accept-Encoding": "gzip,identity",
                "Cookie": cookie
            }

            received_count = 0

            async with websockets.connect(url, additional_headers=headers, ping_interval=1) as ws:
                _ws = ws
                logger.info("WebSocket opened")

                # First subscribe to all titles including DriverList and Heartbeat
                await ws.send(json.dumps({
                    "H": "Streaming",
                    "M": "Subscribe",
                    "A": [SUBS_TITLE + ["DriverList", "Heartbeat"]],
                    "I": 1,
                }))
                
                # Then enter the message receiving loop
                async for message in ws:
                    msg_json = json.loads(message)
                    if not msg_json.get('R'):
                        continue

                    received_count += 1
                    print(received_count)

                    app_state.last_wss_update = datetime.datetime.now()

                    new_snapshot = data_global.copy() if data_global else {}
                    new_data = msg_json['R']
                    new_snapshot.update(new_data)

                    if new_data.get('DriverList'):
                        last_driver_received = datetime.datetime.now()
                        driver_global = new_data.get('DriverList')
                    elif driver_global is not None:
                        new_snapshot['DriverList'] = driver_global
                    else:
                        logger.warning("DriverList not found and driver_global is None")
                    # print("Data received:", data_global)

                    data_global = new_snapshot

                    subscribe_titles = SUBS_TITLE.copy()
                    if driver_global is None:
                        logger.warning("DriverList is None, adding to subscribe list")
                        subscribe_titles.append("DriverList")
                    # elif last_driver_received is None or (datetime.datetime.now() - last_driver_received).total_seconds() > 300:
                    #     logger.info("DriverList is None or not received in the last 5 minutes, resubscribing")
                    #     subscribe_titles.append("DriverList")

                    await asyncio.sleep(0.5)

                    await ws.send(json.dumps({
                        "H": "Streaming",
                        "M": "Subscribe",
                        "A": [subscribe_titles],
                        "I": 1,
                    }))

        except websockets.ConnectionClosed as e:
            logger.warning("WebSocket closed: %s, reconnecting in 5s...", e)
        except Exception as e:
            logger.error("WebSocket error: %s, reconnecting in 5s...", e)

        _ws = None
        logger.info("WebSocket connection closed")
        await asyncio.sleep(5)

def _run_event_loop():
    """Run the asyncio event loop in a dedicated thread."""

    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop.run_until_complete(asyncio.gather(
        connect_wss(),
        monitor_session(),
    ))

def is_connected() -> bool:
    """Check if WebSocket is currently connected."""
    return _ws is not None and _ws.open

def schedule_restart():
    """Schedule a WebSocket reconnect."""
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(restart_wss(), _loop)

async def main():
    await asyncio.gather(connect_wss(), monitor_session())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())