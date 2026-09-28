import wss
from data import *
import liveTiming
import replay

import asyncio
import json
import time
import threading
import logging
from logging.handlers import RotatingFileHandler

from state import app_state

# import fastf1

from quart import Quart, make_response, request
from quart_cors import cors

# from gevent.pywsgi import WSGIServer

app = Quart(__name__)
app = cors(app, allow_origin=['http://localhost:5173', 'https://immastersam.github.io'])

# logger settings
file_handler = RotatingFileHandler(
    'app.log', 
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=3,          # 3 backup files
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s'
))

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

@app.before_serving
async def startup():
    """Startup tasks to run before the server starts."""
    root_logger.info("Starting up the API server...")

    # SignalR WebSocket is no longer available
    # app.add_background_task(wss.connect_wss)
    # app.add_background_task(wss.monitor_session)

@app.route('/stream')
async def stream():

    async def iter_data():
        round = 9
        while True:
            yield 'data:' + json.dumps(get_race(2026, round + 1, 'R')) + '\n\n'
            await asyncio.sleep(5)
            round = (round + 1) % 10 

    response = await make_response(iter_data())
    response.timeout = None
    response.headers['Content-Type'] = 'text/event-stream'
    return response

@app.route('/stream/time')
async def stream_time():

    async def iter_data():
        while True:
            yield 'data:' + json.dumps({'time': time.strftime('%Y-%m-%d %H:%M:%S')}) + '\n\n'
            await asyncio.sleep(5)

    response = await make_response(iter_data())
    response.timeout = None
    response.headers['Content-Type'] = 'text/event-stream'
    return response

@app.route('/stream/live')
async def stream_live():

    async def iter_data():
        
        global client_count

        app_state.client_count += 1
        app.logger.info(f"New client connected from SSE stream (Current clients: {app_state.client_count})")

        # initial connection message
        yield f'data:{json.dumps({"type": "connected", "timestamp": time.time()})}\n\n'

        try:
            while True:

                try:
                    live_data = liveTiming.get_live_timing()
                    if live_data is None:
                        raise Exception("No live data available")
                    else:
                        yield 'data:' + json.dumps(live_data) + '\n\n'

                except Exception as e:
                    root_logger.exception("Error in live timing stream")
                    yield 'data:' + json.dumps({"error": str(e)}) + '\n\n'

                await asyncio.sleep(1)
        except (asyncio.CancelledError, GeneratorExit):
            app_state.client_count -= 1
            app.logger.info(f"Client disconnected from SSE stream (Remaining clients: {app_state.client_count})")
            return 
        except Exception as e:
            root_logger.exception("Unexpected error in SSE stream")

    response = await make_response(iter_data())
    response.timeout = None
    response.headers['Content-Type'] = 'text/event-stream'
    headers = {
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no' # Optional: Disable buffering for Nginx if used as a reverse proxy
    }
    response.headers.update(headers)
    return response

@app.route('/api/replay')
async def api_replay():
    """REST endpoint to get replay data for a completed race session."""
    year = request.args.get('year', type=int, default=None)
    round_number = request.args.get('round', type=int, default=None)
    session_type = request.args.get('session', type=str, default='R')

    try:
        root_logger.info(f"Replay request: year={year}, round={round_number}, session={session_type}")
        data = replay.generate_replay_data(year, round_number, session_type)
        
        # Serialize to JSON and gzip compress
        import gzip
        raw_json = json.dumps(data).encode('utf-8')
        compressed = gzip.compress(raw_json, compresslevel=6)
        
        root_logger.info(f"Replay response compressed to {len(compressed) / 1024 / 1024:.1f}MB")
        
        response = await make_response(compressed)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        response.timeout = None
        return response

    except Exception as e:
        root_logger.exception("Error generating replay data")
        return await make_response(
            json.dumps({'error': str(e)}), 500
        )

if __name__ == '__main__':

    # 檢查並建立 cache 資料夾
    # if not os.path.exists('cache'):
    #     os.makedirs('cache')

    app.run(debug=True)

if __name__ == '__main__':

    # 檢查並建立 cache 資料夾
    # if not os.path.exists('cache'):
    #     os.makedirs('cache')

    app.run(debug=True)