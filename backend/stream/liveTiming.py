# import fastf1
from fastf1.livetiming.data import LiveTimingData
from fastf1.core import Session, Lap
from fastf1.mvapi.api import get_circuit
from fastf1.events import Event

import base64
import zlib
import json
import copy
import datetime
import threading
import time
import logging

import wss

current_session: dict = None

def update_current_session(grandPrix: str, session_type: str) -> bool:
    """Get the current live session""" 

    global current_session

    # Check if the current session is still valid
    current_time = datetime.datetime.now(tz=datetime.timezone.utc)

    if current_session is None:
        current_session = {
            'year': current_time.year,
            'grandPrix': grandPrix,
            'session': session_type,
        }
        return True
    
    current_gp = current_session.get('grandPrix', 'Unknown')
    current_session_type = current_session.get('session', 'Unknown')
    if current_gp != grandPrix or current_session_type != session_type:
        current_session = {
            'year': current_time.year,
            'grandPrix': grandPrix,
            'session': session_type,
        }
        return True
    
    return False
            
def decompressed_carData(car_raw_data: dict) -> dict:
    """Decompress the car data from the raw data"""

    if not car_raw_data:
        return {}

    compressed_bytes = base64.b64decode(car_raw_data)
    decompressed_data = zlib.decompress(compressed_bytes, -zlib.MAX_WBITS)
    car_data = json.loads(decompressed_data.decode('utf-8'))

    return car_data.get('Entries', [0])[-1].get('Cars', {})

def decompressed_posData(pos_raw_data: dict) -> dict:
    """Decompress the car data from the raw data"""

    if not pos_raw_data:
        return {}

    compressed_bytes = base64.b64decode(pos_raw_data)
    decompressed_data = zlib.decompress(compressed_bytes, -zlib.MAX_WBITS)
    position_data = json.loads(decompressed_data.decode('utf-8'))

    return position_data.get('Position', [0])[-1].get('Entries', {})

def get_circuit_corners(circuit: dict) -> list:
    """Get the circuit corners from the current session"""

    if circuit is None:
        return []
    
    circuit_corners = circuit.get('corners', [])

    corners = []
    for corner in circuit_corners:
        corners.append({
            'x': float(corner.get('trackPosition', {}).get('x', 0)),
            'y': float(corner.get('trackPosition', {}).get('y', 0)),
            'number': int(corner.get('number', 0)),
            'angle': float(corner.get('angle', 0)),
        })

    return corners

def get_track_path(circuit: dict) -> list[tuple[float, float]]:
    """Get the track path from the multiview API (fastf1.mvapi)"""

    path = []

    for (x, y) in zip(circuit.get('x', []), circuit.get('y', [])):
        path.append((float(x), float(y)))

    return path

def get_driver_segment_position(track_path: list[tuple[float, float]], drivers_raw_data: dict, timing_raw_data: dict) -> list[dict]:
    """Get the driver position base on the segment data"""

    driver_positions = []

    for driver_number in drivers_raw_data.keys():

        if not driver_number.isdigit():
            continue

        # Get driver lap segment info
        driver_info = get_driver_info(driver_number, drivers_raw_data)
        driver_timing_info = timing_raw_data.get('Lines', {}).get(driver_number, {})
        driver_segments = []
        for sector in driver_timing_info.get('Sectors', []):
            driver_segments.extend(sector.get('Segments', []))

        # look for the last segment with status > 0
        last_segment = None
        for segment_id in range(len(driver_segments) - 1, -1, -1):
            if driver_segments[segment_id].get('Status', 0) > 0:
                last_segment = segment_id
                break

        segment_position = track_path[last_segment * (len(track_path) // len(driver_segments))] if last_segment is not None else track_path[0]
        position = {
            'x': float(segment_position[0]),
            'y': float(segment_position[1]),
        }

        driver_position = {
            'driver': driver_info,
            'position': position,
        }

        driver_positions.append(driver_position)
    
    return driver_positions

def get_driver_position(pos_data: dict, driver_raw_data: dict) -> list[dict]:
    """Get the driver position from the position data and driver raw data"""

    driver_positions = []

    for (driver_number, pos_info) in pos_data.items():
        if driver_number not in driver_raw_data:
            continue
        
        driver_info = get_driver_info(driver_number, driver_raw_data)
        position = {
            'x': float(pos_info.get('X', 0)),
            'y': float(pos_info.get('Y', 0)),
        }

        driver_position = {
            'driver': driver_info,
            'position': position,
        }

        driver_positions.append(driver_position)

    return driver_positions

def get_circuit_info(meeting_data: dict, pos_data: dict, drivers_raw_data: dict, timing_raw_data: dict) -> dict:
    """Get the current circuit info"""

    circuit_key = int(meeting_data.get('Circuit', {}).get('Key', 0))
    current_time = datetime.datetime.now(tz=datetime.timezone.utc)
    circuit = get_circuit(year=current_time.year, circuit_key=circuit_key)

    track_path = get_track_path(circuit)
    driver_position = get_driver_segment_position(track_path, drivers_raw_data, timing_raw_data)

    circuit = {
        'trackName': meeting_data.get('Circuit', {}).get('ShortName', 'Unknown'),
        'corners': get_circuit_corners(circuit),
        'trackPath': track_path,
        'driverPos': driver_position,
        'rotation': float(circuit.get('rotation', 0)),
    }

    return circuit
            
def get_driver_info(driver_number: str, drivers_raw_data: dict) -> dict:
    """Get the driver info for a given driver number"""

    driver_raw_data = drivers_raw_data.get(driver_number, {})

    driver_data = { 'driverNumber': int(driver_raw_data.get('RacingNumber', driver_number)),
                    'driverFullName': driver_raw_data.get('FullName', 'Unknown'),
                    'driverAbbreviation': driver_raw_data.get('Tla', '???'), 
                    'driverTeamColor': driver_raw_data.get('TeamColour', 'FFFFFF'),}

    return driver_data

def get_drspit_info(driver_timing_info: dict, car_info: dict) -> dict:
    """Get the DRS info for a driver"""

    # DRS
    # DRS_ENABLED = {10, 12, 14}

    drs_raw = car_info.get('45', 0)
    if drs_raw > 9:
        drs_status = 2  # DRS is enabled
    elif drs_raw == 8:
        drs_status = 1  # DRS is ready
    else:
        drs_status = 0

    # PIT
    inPit = driver_timing_info.get('InPit', False)
    PitOut = driver_timing_info.get('PitOut', False)

    if inPit:
        pit_status = 1  # In pit
    elif PitOut:
        pit_status = 2  # Out of pit
    else:
        pit_status = 0

    drspit_info = { 'drsStatus': drs_status,
                 'pitStatus': pit_status}

    return drspit_info

def get_driver_status(driver_timing_info: dict, entries: int = 999) -> dict:
    """Get the current status of a driver"""

    status = {'retired': driver_timing_info.get('Retired', True),
              'stopped': driver_timing_info.get('Stopped', True),
              'knockedOut': driver_timing_info.get('KnockedOut', False),
              'danger': int(driver_timing_info.get('Position', 99)) > entries,}
    
    return status

def get_current_tire_info(driver_number: str, tire_raw_data: dict) -> dict:
    """Get the current tire info for a driver"""

    driver_tire_info = tire_raw_data.get('Lines', {}).get(driver_number, {})

    try:
        last_stint = driver_tire_info.get('Stints', {})[-1]
    except (IndexError, TypeError, KeyError):
        last_stint = {}

    compound = last_stint.get('Compound', 'UNKNOWN')
    if compound not in {'SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'}:
        compound = 'UNKNOWN'

    tire_info = { 'compound': compound,
                  'laps': int(last_stint.get('TotalLaps', '0'))}
    
    return tire_info

def get_gap_info(driver_timing_info: dict, session: str, session_part: str = '') -> dict:
    """Get the current gap info for a driver to the leader and the driver in front"""

    if session == 'Qualifying' or session == 'Sprint Qualifying':
        # In qualifying, the gap info is in the stats
        driver_stats = driver_timing_info.get('Stats', {})[int(session_part) - 1]

        gap_info = { 'toLeader': driver_stats.get('TimeDiffToFastest', '-- ---'),
                     'toFront': driver_stats.get('TimeDifftoPositionAhead', '-- ---')}

    # Else they are in the timing data    
    elif session == 'Race' or session == 'Sprint':
        gap_info = { 'toLeader': driver_timing_info.get('GapToLeader', '-- ---'),
                     'toFront': driver_timing_info.get('IntervalToPositionAhead', {'Value': '-- ---'}).get('Value', '-- ---')}
    elif session.startswith('Practice'):
        gap_info = { 'toLeader': driver_timing_info.get('TimeDiffToFastest', '-- ---'),
                     'toFront': driver_timing_info.get('TimeDiffToPositionAhead', '-- ---')}
    else:
        gap_info = { 'toLeader': '-- ---',
                     'toFront': '-- ---'}
    
    return gap_info

def get_lap_info(driver_stats_info: dict, driver_timing_info: dict) -> dict:
    """Get the lap time info for a driver"""

    lastLap_info = driver_timing_info.get('LastLapTime', {'Value': ''})
    lastLap = { 'lapTime': lastLap_info.get('Value', '-- ---'),
                'overallFastest': lastLap_info.get('OverallFastest', False),
                'personalFastest': lastLap_info.get('PersonalFastest', False)}
    
    bestLap_info = driver_stats_info.get('PersonalBestLapTime', {'Value': ''})
    bestLap = { 'lapTime': bestLap_info.get('Value', '-- ---'),
                'overallFastest': bestLap_info.get('Position', 0) == 1,
                'personalFastest': bestLap_info.get('PersonalFastest', False)}

    lap_info = { 'lastLap': lastLap,
                 'bestLap': bestLap}

    return lap_info

def get_sector_info(driver_stats_info: dict, driver_timing_info: dict) -> list:
    """Get the sector info for a driver"""

    sectors = []

    for i in range(3):
        sector_last_info = driver_timing_info.get(f'Sectors')[i]
        sector_best_info = driver_stats_info.get(f'BestSectors')[i]

        sector_last_sectorTime = sector_last_info.get('Value', '-- ---')
        sector_best_sectorTime = sector_best_info.get('Value', '-- ---')

        sector_last = { 'sectorTime': sector_last_sectorTime if sector_last_sectorTime != '' else '-- ---',
                        'previousSectorTime': sector_last_info.get('PreviousValue', '-- ---'),
                        'overallFastest': sector_last_info.get('OverallFastest', False),
                        'personalFastest': sector_last_info.get('PersonalFastest', False)}
        
        sector_best = { 'sectorTime': sector_best_sectorTime if sector_best_sectorTime != '' else '-- ---',
                        'previousSectorTime': sector_best_info.get('PreviousValue', '-- ---'),
                        'overallFastest': sector_best_info.get('Position', 0) == 1,
                        'personalFastest': sector_best_info.get('PersonalFastest', False)}

        sector_data = { 'sectorLast': sector_last,
                        'sectorBest': sector_best,
                        'segments': [segment.get('Status') for segment in sector_last_info.get('Segments', [])]}

        sectors.append(sector_data)
    
    return sectors

def get_weather_info(weather_raw_data: dict) -> dict:
    """Get the current weather info"""

    weather_info = { 'airTemp': float(weather_raw_data.get('AirTemp', '0')),
                     'humidity': float(weather_raw_data.get('Humidity', '0')),
                     'pressure': float(weather_raw_data.get('Pressure', '0')),
                     'rainfall': weather_raw_data.get('Rainfall', '0') == '1',
                     'trackTemp': float(weather_raw_data.get('TrackTemp', '0')),
                     'windDirection': int(weather_raw_data.get('WindDirection', '0')),
                     'windSpeed': float(weather_raw_data.get('WindSpeed', '0')) * 3.6}

    return weather_info

def get_extrapolated_clock(clock_raw_data: dict) -> dict:

    remaining_time = clock_raw_data.get('Remaining', '00:00:00')
    h, m, s = map(int, remaining_time.split(':'))
    remaining_seconds = h * 3600 + m * 60 + s

    clock = {
        'remaining': remaining_seconds,
        'extrapolating': clock_raw_data.get('Extrapolating', False)
    }

    return clock

def get_team_radio_info(radio_raw_data: dict, session_raw_data: dict, drivers_raw_data: dict) -> list:
    """Get the team radio info"""

    team_radio = []
    radio_messages = radio_raw_data.get('Captures', [])[::-1]
    session_path = session_raw_data.get('Path', '')

    # Convert radio messages to the desired format
    for message in radio_messages:
        audio_path = message.get('Path', '')
        radio = {
            'Path': f"https://livetiming.formula1.com/static/{session_path}{audio_path}",
            'Utc': message.get('Utc', ''),
            'driver': get_driver_info(message.get('RacingNumber', '0'), drivers_raw_data),
        }

        team_radio.append(radio)

    return team_radio


def get_live_timing() -> dict:
    """Get the live timing data from the WebSocket connection"""

    global current_session 
    logger = logging.getLogger(__name__)

    # Load current session
    # session: Session = current_session.get('session')

    snapshot = copy.deepcopy(wss.data_global)

    res = dict()
    
    try:
        drivers_raw_data: dict = snapshot['DriverList']
        timing_raw_data: dict = snapshot['TimingData']
        stats_raw_data: dict = snapshot['TimingStats']
        tire_raw_data: dict = snapshot['TimingAppData']
        weather_raw_data: dict = snapshot['WeatherData']
        trackStatus_raw_data: dict = snapshot['TrackStatus']
        clock_raw_data: dict = snapshot.get('ExtrapolatedClock', {})
        session_raw_data: dict = snapshot['SessionInfo']
        car_raw_data: dict = snapshot.get('CarData.z', {})
        pos_raw_data: dict = snapshot.get('Position.z', {})
        raceControlMessages_raw_data: dict = snapshot.get('RaceControlMessages', {})
        radio_raw_data: dict = snapshot.get('TeamRadio', {})
    except Exception as e:
        logging.exception("Error retrieving live timing data")
        return res
    
    meeting_data: dict = session_raw_data.get('Meeting', {})
    
    res['grandPrixName'] = meeting_data.get('Name', 'Unknown')
    res['country'] = meeting_data.get('Country', {}).get('Name', 'Unknown')
    
    session_type = session_raw_data.get('Type', 'Unknown')
    res['session'] = session_raw_data.get('Name', 'Unknown')
    
    # update current session
    if update_current_session(res['grandPrixName'], session_type):
        wss.schedule_restart()
        logger.info("Current session updated successfully.")
    
    position_data = decompressed_posData(pos_raw_data)
    res['circuit'] = get_circuit_info(meeting_data, position_data, drivers_raw_data, timing_raw_data)
    
    # Qualifying handling
    session_part = timing_raw_data.get('SessionPart', '')
    if session_type == 'Qualifying':
        # In qualifying, entries marks the number of drivers that are allowed to qualify
        entries = timing_raw_data.get('NoEntries', [])[int(session_part) % 3]
        if res['session'] == 'Sprint Qualifying':
            res['session'] += f' SQ{session_part}'
        else:
            res['session'] += f' Q{session_part}'
    else:
        entries = 999
    
    

    # Race handling
    if session_type == 'Race':
        lapCount_raw_data: dict = snapshot['LapCount']
        res['other'] = { 'currentLap': int(lapCount_raw_data.get('CurrentLap', 0)),
                        'totalLaps': int(lapCount_raw_data.get('TotalLaps', 0))}
        
    # Get car data
    car_data = decompressed_carData(car_raw_data)

    # Get evey driver's current result
    result_list = []
    for (driverNumber, data) in timing_raw_data.get('Lines', {}).items():

        driver_timing_info = timing_raw_data.get('Lines', {}).get(driverNumber, {})
        driver_stats_info = stats_raw_data.get('Lines', {}).get(driverNumber, {})
        car_info = car_data.get(driverNumber, {}).get('Channels', {})

        driver_result = { 'driver': get_driver_info(driverNumber, drivers_raw_data),
                        'position': int(data.get('Position', 9999)),
                        'drspit': get_drspit_info(driver_timing_info, car_info),
                        'status': get_driver_status(driver_timing_info, entries),
                        'tire': get_current_tire_info(driverNumber, tire_raw_data),
                        'Gap': get_gap_info(driver_timing_info, session_type, session_part),
                        'lapTime': get_lap_info(driver_stats_info, driver_timing_info),
                        'sectors': get_sector_info(driver_stats_info, driver_timing_info)}
        
        result_list.append(driver_result)

    result_list.sort(key=lambda x: x['position'])
    res['results'] = result_list

    # Get the current track status
    res['trackStatus'] = { 'status': int(trackStatus_raw_data.get('Status', '0')),
                        'message': trackStatus_raw_data.get('Message', 'Unknown')}

    # Get the current weather info
    res['weather'] = get_weather_info(weather_raw_data)

    # Get the extrapolated clock info
    res['clock'] = get_extrapolated_clock(clock_raw_data)

    # Get the extrapolated clock info
    res['raceControlMessages'] = raceControlMessages_raw_data.get('Messages', [])[::-1]

    # Get the radio info
    res['teamRadio'] = get_team_radio_info(radio_raw_data, session_raw_data, drivers_raw_data)
    
    return res

if __name__ == '__main__':

    t = threading.Thread(target=wss.connect_wss, daemon=True)
    t.start()

    # fastf1.Cache.enable_cache('cache')

    while True:
        print("Getting live timing data...")
        # try:
            # res = get_live_timing()
            # print(*res['results'], sep='\n')
        current_data = get_live_timing()
        json.dump(current_data, open('saved_data 2026.txt', 'w'), indent=4)
        if current_data:
            exit(0)
            # raw_car_data = wss.data_global.get('Position.z')
            # compressed_bytes = base64.b64decode(raw_car_data)
            # decompressed_data = zlib.decompress(compressed_bytes, -zlib.MAX_WBITS)
            # car_data = json.loads(decompressed_data.decode('utf-8'))
            # print(car_data)
        # except Exception as e:
        #     print(f"Error getting live timing data: {e}")
            
        time.sleep(3)

    