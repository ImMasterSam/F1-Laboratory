import fastf1

from fastf1.livetiming.data import LiveTimingData



async def load_current_session():

    while True:
        try:
            session = fastf1.get_events_remaining()
            if session is not None:
                session.load(laps=False, weather=False, telemetry=False)
                return session
        except Exception as e:
            print(f"Error loading current session: {e}")

def get_race(year: int, round_number: int, session_type: str) -> list[str]:
    
    session = fastf1.get_session(year, round_number, session_type)
    session.load(laps=False, weather=False, telemetry=False)

    res = dict()
    res['drivers'] = session.drivers
    res['Grand Prix'] = session.event['EventName']

    return res

def get_live_timing_data(year: int, round_number: int, session_type: str):
    livedata = LiveTimingData('backend/cache/saved_data.txt')
    session = fastf1.get_testing_session(year, round_number, session_type)
    session.load(livedata=livedata)

    res = dict()
    res['drivers'] = session.drivers
    res['Grand Prix'] = session.event['EventName']

    return res