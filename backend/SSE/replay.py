"""
replay.py - F1 比賽回放資料生成模組

使用 fastf1 載入歷史比賽資料，生成按時間序的 dashData_type 快照序列，
供前端進行回放。每個快照都包含完整的 dashData_type 結構。
"""

import fastf1
from fastf1.mvapi.api import get_circuit

import pandas as pd
import numpy as np
import json
import logging
import datetime
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Enable fastf1 cache (resolve path relative to this file's directory)
_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cache', 'fastf1')
os.makedirs(_cache_dir, exist_ok=True)
fastf1.Cache.enable_cache(_cache_dir)

# ─── Cache for generated replay data ───
_replay_cache: dict = {}


def _format_timedelta(td: pd.Timedelta) -> str:
    """Format a pandas Timedelta to a lap time string like '1:23.456'"""
    if pd.isna(td):
        return '-- ---'
    total_seconds = td.total_seconds()
    if total_seconds <= 0:
        return '-- ---'
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    if minutes > 0:
        return f'{minutes}:{seconds:06.3f}'
    else:
        return f'{seconds:.3f}'


def _get_latest_completed_round() -> tuple[int, int, str]:
    """Get the latest completed race round.
    Returns (year, round_number, event_name)
    """
    now = pd.Timestamp.utcnow().tz_localize(None)
    year = now.year
    schedule = fastf1.get_event_schedule(year)
    past_events = schedule[schedule['Session5DateUtc'] < now]

    if past_events.empty:
        # Try previous year
        year -= 1
        schedule = fastf1.get_event_schedule(year)
        past_events = schedule[schedule['Session5DateUtc'] < now]

    latest = past_events.iloc[-1]
    return year, int(latest['RoundNumber']), latest['EventName']


def _dict_to_array(d):
    if not d:
        return []
    max_idx = max(d.keys())
    return [d.get(i, 0) for i in range(max_idx + 1)]


def _build_segments_timeline(session) -> list:
    from fastf1._api import fetch_page, parse
    import pandas as pd
    import copy

    try:
        page_content = fetch_page(session.api_path, 'timing_data')
        if not page_content:
            return []
        records = parse(page_content)
    except Exception as e:
        logger.error(f"Failed to fetch timing_data for segments: {e}")
        return []

    state = {}
    timeline = []

    for rec in records:
        if len(rec) < 2:
            continue
        time_str, data = rec[0], rec[1]
        if not time_str or not data:
            continue

        try:
            t = pd.to_timedelta(time_str).total_seconds()
        except Exception:
            continue

        updated = False
        if 'Lines' in data:
            for drv, drv_data in data['Lines'].items():
                if drv not in state:
                    state[drv] = {0: {}, 1: {}, 2: {}}

                if 'Sectors' in drv_data:
                    sectors = drv_data['Sectors']
                    if isinstance(sectors, dict):
                        items = sectors.items()
                    elif isinstance(sectors, list):
                        items = enumerate(sectors)
                    else:
                        items = []

                    for sec_idx, sec_data in items:
                        s_idx = int(sec_idx)
                        if isinstance(sec_data, dict) and 'Segments' in sec_data:
                            segments = sec_data['Segments']
                            if isinstance(segments, dict):
                                seg_items = segments.items()
                            elif isinstance(segments, list):
                                seg_items = enumerate(segments)
                            else:
                                seg_items = []

                            for seg_idx, seg_data in seg_items:
                                if isinstance(seg_data, dict) and 'Status' in seg_data:
                                    state[drv][s_idx][int(seg_idx)] = seg_data['Status']
                                    updated = True

        if updated:
            timeline.append({
                'time': t,
                'data': copy.deepcopy(state)
            })

    return timeline


def generate_replay_data(year: int = None, round_number: int = None,
                          session_type: str = 'R') -> dict:
    """
    Generate the full replay data for a session.

    Returns a dict with:
      - metadata: { grandPrixName, session, country, totalDuration, totalLaps, ... }
      - snapshots: list of dashData_type dicts, one per second
    """
    cache_key = f"{year}_{round_number}_{session_type}"
    if cache_key in _replay_cache:
        logger.info(f"Using cached replay data for {cache_key}")
        return _replay_cache[cache_key]

    # If no year/round specified, use latest completed race
    if year is None or round_number is None:
        year, round_number, _ = _get_latest_completed_round()
        cache_key = f"{year}_{round_number}_{session_type}"
        if cache_key in _replay_cache:
            return _replay_cache[cache_key]

    logger.info(f"Generating replay data for {year} Round {round_number} ({session_type})")

    # Load session
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, weather=True, laps=True)

    # ─── Basic session info ───
    event = session.event
    grand_prix_name = event['EventName']
    country = event['Country']
    session_name = session.name
    total_laps = session.total_laps or 0

    # ─── Build circuit data (static, same for all snapshots) ───
    circuit_data = _build_circuit_data(session)

    # ─── Prepare per-second position data for all drivers ───
    pos_data_resampled = _resample_position_data(session)

    # ─── Build per-lap driver state (position, lap time, tire, sectors, etc.) ───
    driver_lap_states = _build_driver_lap_states(session)

    # ─── Build weather timeline ───
    weather_timeline = _build_weather_timeline(session)

    # ─── Build track status timeline ───
    track_status_timeline = _build_track_status_timeline(session)

    # ─── Build race control messages timeline ───
    rcm_timeline = _build_rcm_timeline(session)
    segments_timeline = _build_segments_timeline(session)

    # ─── Determine time range ───
    session_start = session.session_start_time
    all_pos_times = []
    for drv_num, df in pos_data_resampled.items():
        if not df.empty:
            all_pos_times.extend(df.index.tolist())

    if all_pos_times:
        max_session_time = max(all_pos_times)
    else:
        # Fallback: use last lap time
        max_session_time = session.laps['Time'].max().total_seconds()

    total_duration_seconds = int(max_session_time - session_start.total_seconds())
    if total_duration_seconds <= 0:
        total_duration_seconds = 5400  # fallback 90 min

    logger.info(f"Generating {total_duration_seconds} snapshots "
                f"(session_start={session_start}, duration={total_duration_seconds}s)")

    # ─── Generate snapshots ───
    snapshots = []
    start_sec = int(session_start.total_seconds())

    # Get driver info (static)
    driver_info_map = _build_driver_info_map(session)

    for t in range(total_duration_seconds):
        current_session_time = start_sec + t  # seconds from session recording start

        snapshot = _build_snapshot(
            t=t,
            current_session_time=current_session_time,
            grand_prix_name=grand_prix_name,
            session_name=session_name,
            country=country,
            total_laps=total_laps,
            circuit_data=circuit_data,
            pos_data_resampled=pos_data_resampled,
            driver_lap_states=driver_lap_states,
            driver_info_map=driver_info_map,
            weather_timeline=weather_timeline,
            track_status_timeline=track_status_timeline,
            rcm_timeline=rcm_timeline,
            segments_timeline=segments_timeline,
            session=session,
        )
        snapshots.append(snapshot)

    result = {
        'metadata': {
            'grandPrixName': grand_prix_name,
            'session': session_name,
            'country': country,
            'totalDuration': total_duration_seconds,
            'totalLaps': total_laps,
            'year': year,
            'round': round_number,
        },
        'snapshots': snapshots,
    }

    _replay_cache[cache_key] = result
    logger.info(f"Replay data generated: {len(snapshots)} snapshots")
    return result


def _build_circuit_data(session) -> dict:
    """Build static circuit data (track path, corners, rotation)."""

    try:
        circuit_info = session.get_circuit_info()
        circuit_key = session.session_info['Meeting']['Circuit']['Key']
        circuit_raw = get_circuit(year=session.event['EventDate'].year,
                                  circuit_key=circuit_key)

        track_path = list(zip(
            [float(x) for x in circuit_raw.get('x', [])],
            [float(y) for y in circuit_raw.get('y', [])]
        ))

        corners = []
        for _, c in circuit_info.corners.iterrows():
            corners.append({
                'x': float(c['X']),
                'y': float(c['Y']),
                'number': int(c['Number']),
                'angle': float(c['Angle']),
            })

        rotation = float(circuit_raw.get('rotation', 0))
        track_name = session.session_info.get('Meeting', {}).get('Circuit', {}).get('ShortName', 'Unknown')

    except Exception as e:
        logger.error(f"Error building circuit data: {e}")
        track_path = []
        corners = []
        rotation = 0
        track_name = 'Unknown'

    return {
        'trackName': track_name,
        'corners': corners,
        'trackPath': track_path,
        'rotation': rotation,
    }


def _resample_position_data(session) -> dict:
    """
    Resample position data to 1Hz (one point per second) for all drivers.
    Returns { driver_number_str: DataFrame indexed by session_time_seconds }
    """
    pos_data = session.pos_data
    resampled = {}

    for drv_num_str in session.drivers:
        drv_num = str(drv_num_str)
        if drv_num not in pos_data:
            resampled[drv_num] = pd.DataFrame()
            continue

        df = pos_data[drv_num].copy()
        if df.empty:
            resampled[drv_num] = pd.DataFrame()
            continue

        # Convert SessionTime to seconds
        df['session_seconds'] = df['SessionTime'].dt.total_seconds()
        df = df.set_index('session_seconds')

        # Resample to 1Hz using interpolation
        min_t = int(df.index.min())
        max_t = int(df.index.max())
        new_index = np.arange(min_t, max_t + 1, 1.0)

        df_resampled = pd.DataFrame(index=new_index)
        for col in ['X', 'Y']:
            df_resampled[col] = np.interp(new_index, df.index.values, df[col].values)

        resampled[drv_num] = df_resampled

    return resampled


def _build_driver_info_map(session) -> dict:
    """Build driver info map { driver_number_str: driver_info_dict }"""
    info_map = {}
    for drv_num_str in session.drivers:
        drv = session.get_driver(drv_num_str)
        info_map[drv_num_str] = {
            'driverNumber': int(drv_num_str),
            'driverFullName': drv['FullName'],
            'driverAbbreviation': drv['Abbreviation'],
            'driverTeamColor': drv['TeamColor'],
        }
    return info_map


def _build_driver_lap_states(session) -> dict:
    """
    Build per-driver, per-lap state info.
    Returns { driver_number_str: [{ lap_number, position, lap_time, sectors, ... }, ...] }
    Each entry includes the session time when the lap ended.
    """
    laps = session.laps
    states = {}

    # Pre-compute best lap times and best sector times per session
    all_best_lap = laps['LapTime'].min()
    all_best_s1 = laps['Sector1Time'].min()
    all_best_s2 = laps['Sector2Time'].min()
    all_best_s3 = laps['Sector3Time'].min()

    for drv_num_str in session.drivers:
        drv_laps = laps.pick_drivers(drv_num_str).sort_values('LapNumber')
        driver_states = []
        personal_best_lap = pd.NaT
        personal_best_s1 = pd.NaT
        personal_best_s2 = pd.NaT
        personal_best_s3 = pd.NaT

        for _, lap in drv_laps.iterrows():
            lap_time = lap['LapTime']
            s1_time = lap['Sector1Time']
            s2_time = lap['Sector2Time']
            s3_time = lap['Sector3Time']

            # Track personal bests
            is_pb_lap = False
            is_pb_s1 = False
            is_pb_s2 = False
            is_pb_s3 = False

            if pd.notna(lap_time):
                if pd.isna(personal_best_lap) or lap_time < personal_best_lap:
                    personal_best_lap = lap_time
                    is_pb_lap = True

            if pd.notna(s1_time):
                if pd.isna(personal_best_s1) or s1_time < personal_best_s1:
                    personal_best_s1 = s1_time
                    is_pb_s1 = True

            if pd.notna(s2_time):
                if pd.isna(personal_best_s2) or s2_time < personal_best_s2:
                    personal_best_s2 = s2_time
                    is_pb_s2 = True

            if pd.notna(s3_time):
                if pd.isna(personal_best_s3) or s3_time < personal_best_s3:
                    personal_best_s3 = s3_time
                    is_pb_s3 = True

            # Determine when this lap ended (session time in seconds)
            lap_end_time = lap['Time']
            if pd.notna(lap_end_time):
                lap_end_seconds = lap_end_time.total_seconds()
            else:
                lap_end_seconds = None

            # Sector session times (when each sector was completed)
            s1_end = lap['Sector1SessionTime']
            s2_end = lap['Sector2SessionTime']
            s3_end = lap['Sector3SessionTime']

            state = {
                'lapNumber': int(lap['LapNumber']) if pd.notna(lap['LapNumber']) else 0,
                'position': int(lap['Position']) if pd.notna(lap['Position']) else 99,
                'lapEndSeconds': lap_end_seconds,
                'sectorEndSeconds': [
                    s1_end.total_seconds() if pd.notna(s1_end) else None,
                    s2_end.total_seconds() if pd.notna(s2_end) else None,
                    s3_end.total_seconds() if pd.notna(s3_end) else None,
                ],
                'lapTime': {
                    'lastLap': {
                        'lapTime': _format_timedelta(lap_time),
                        'overallFastest': pd.notna(lap_time) and pd.notna(all_best_lap) and lap_time == all_best_lap,
                        'personalFastest': is_pb_lap,
                    },
                    'bestLap': {
                        'lapTime': _format_timedelta(personal_best_lap),
                        'overallFastest': pd.notna(personal_best_lap) and pd.notna(all_best_lap) and personal_best_lap == all_best_lap,
                        'personalFastest': True,
                    },
                },
                'sectors': [
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s1_time),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(s1_time) and pd.notna(all_best_s1) and s1_time == all_best_s1,
                            'personalFastest': is_pb_s1,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s1),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(personal_best_s1) and pd.notna(all_best_s1) and personal_best_s1 == all_best_s1,
                            'personalFastest': True,
                        },
                        'segments': [],
                    },
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s2_time),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(s2_time) and pd.notna(all_best_s2) and s2_time == all_best_s2,
                            'personalFastest': is_pb_s2,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s2),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(personal_best_s2) and pd.notna(all_best_s2) and personal_best_s2 == all_best_s2,
                            'personalFastest': True,
                        },
                        'segments': [],
                    },
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s3_time),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(s3_time) and pd.notna(all_best_s3) and s3_time == all_best_s3,
                            'personalFastest': is_pb_s3,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s3),
                            'previousSectorTime': '-- ---',
                            'overallFastest': pd.notna(personal_best_s3) and pd.notna(all_best_s3) and personal_best_s3 == all_best_s3,
                            'personalFastest': True,
                        },
                        'segments': [],
                    },
                ],
                'compound': lap['Compound'] if pd.notna(lap['Compound']) else 'UNKNOWN',
                'tyreLife': int(lap['TyreLife']) if pd.notna(lap['TyreLife']) else 0,
                'stint': int(lap['Stint']) if pd.notna(lap['Stint']) else 1,
                'pitIn': pd.notna(lap['PitInTime']),
                'pitOut': pd.notna(lap['PitOutTime']),
            }
            driver_states.append(state)

        states[drv_num_str] = driver_states

    return states


def _build_weather_timeline(session) -> list:
    """Build weather data indexed by session time in seconds."""
    wd = session.weather_data
    timeline = []
    for _, row in wd.iterrows():
        t = row['Time'].total_seconds()
        timeline.append({
            'time': t,
            'data': {
                'airTemp': float(row['AirTemp']),
                'humidity': float(row['Humidity']),
                'pressure': float(row['Pressure']),
                'rainfall': bool(row['Rainfall']),
                'trackTemp': float(row['TrackTemp']),
                'windDirection': int(row['WindDirection']),
                'windSpeed': float(row['WindSpeed']) * 3.6,  # m/s to km/h
            }
        })
    return timeline


def _build_track_status_timeline(session) -> list:
    """Build track status timeline indexed by session time in seconds."""
    ts = session.track_status
    status_map = {
        '1': 1, '2': 2, '4': 4, '5': 5, '6': 6, '7': 7,
        'AllClear': 1, 'Yellow': 2, 'SCDeployed': 4,
        'Red': 5, 'VSCDeployed': 6, 'VSCEnding': 7,
    }
    timeline = []
    for _, row in ts.iterrows():
        t = row['Time'].total_seconds()
        status_code = status_map.get(str(row['Status']), int(row['Status']) if str(row['Status']).isdigit() else 0)
        timeline.append({
            'time': t,
            'data': {
                'status': status_code,
                'message': row['Message'],
            }
        })
    return timeline


def _build_rcm_timeline(session) -> list:
    """Build race control messages timeline."""
    rcm = session.race_control_messages
    t0 = session.t0_date
    timeline = []

    for _, row in rcm.iterrows():
        # RCM 'Time' is absolute datetime, convert to session time
        msg_time = row['Time']
        if pd.notna(msg_time):
            if hasattr(msg_time, 'total_seconds'):
                session_seconds = msg_time.total_seconds()
            else:
                # It's a datetime
                delta = msg_time - t0
                session_seconds = delta.total_seconds()
        else:
            session_seconds = 0

        timeline.append({
            'time': session_seconds,
            'data': {
                'Utc': str(msg_time) if pd.notna(msg_time) else '',
                'Lap': int(row['Lap']) if pd.notna(row.get('Lap')) else 0,
                'Category': row.get('Category', ''),
                'Flag': row.get('Flag') if pd.notna(row.get('Flag')) else None,
                'Scope': row.get('Scope') if pd.notna(row.get('Scope')) else None,
                'Message': row.get('Message', ''),
            }
        })

    return timeline


def _get_current_value(timeline: list, current_time: float) -> Optional[dict]:
    """Get the latest value from a timeline at the given session time."""
    result = None
    for entry in timeline:
        if entry['time'] <= current_time:
            result = entry['data']
        else:
            break
    return result


def _get_accumulated_messages(timeline: list, current_time: float) -> list:
    """Get all messages up to the given session time, most recent first."""
    messages = []
    for entry in timeline:
        if entry['time'] <= current_time:
            messages.append(entry['data'])
    return messages[::-1]  # Most recent first


def _get_driver_state_at_time(driver_states: list, current_session_time: float) -> Optional[dict]:
    """Get the latest lap state for a driver at the given session time."""
    result = None
    for state in driver_states:
        if state['lapEndSeconds'] is not None and state['lapEndSeconds'] <= current_session_time:
            result = state
        elif state['lapEndSeconds'] is None:
            # First lap may not have end time, use it as initial state
            if result is None:
                result = state
    return result


def _compute_gap_to_leader(results: list) -> list:
    """Compute gap to leader and interval to position ahead for race."""
    if not results:
        return results

    # Sort by position
    results.sort(key=lambda x: x['position'])

    leader_time = None
    prev_time = None

    for r in results:
        lap_end = r.get('_lapEndSeconds')
        if leader_time is None:
            leader_time = lap_end
            r['Gap'] = {'toLeader': '', 'toFront': ''}
        else:
            if lap_end is not None and leader_time is not None:
                gap_to_leader = lap_end - leader_time
                gap_str = f'+{gap_to_leader:.3f}' if gap_to_leader > 0 else ''
            else:
                gap_str = '-- ---'

            if lap_end is not None and prev_time is not None:
                interval = lap_end - prev_time
                interval_str = f'+{interval:.3f}' if interval > 0 else ''
            else:
                interval_str = '-- ---'

            r['Gap'] = {'toLeader': gap_str, 'toFront': interval_str}

        prev_time = lap_end

    return results


def _build_snapshot(t: int, current_session_time: float,
                    grand_prix_name: str, session_name: str, country: str,
                    total_laps: int, circuit_data: dict,
                    pos_data_resampled: dict, driver_lap_states: dict,
                    driver_info_map: dict, weather_timeline: list,
                    track_status_timeline: list, rcm_timeline: list,
                    segments_timeline: list, session) -> dict:
    """Build a single snapshot at time t (seconds from race start)."""

    # ─── Driver positions on track ───
    driver_positions = []
    for drv_num, df in pos_data_resampled.items():
        if df.empty or current_session_time not in df.index:
            continue
        row = df.loc[current_session_time]
        if drv_num in driver_info_map:
            driver_positions.append({
                'driver': driver_info_map[drv_num],
                'position': {
                    'x': float(row['X']),
                    'y': float(row['Y']),
                },
            })

    # ─── Circuit with current driver positions ───
    circuit = {
        **circuit_data,
        'driverPos': driver_positions,
    }

    # ─── Segments ───
    current_segments = _get_current_value(segments_timeline, current_session_time) or {}

    # ─── Driver results (position, lap time, tire, etc.) ───
    results = []
    current_lap = 0

    for drv_num in driver_info_map.keys():
        drv_states = driver_lap_states.get(drv_num, [])
        state = _get_driver_state_at_time(drv_states, current_session_time)

        if state is None:
            # Driver hasn't started yet, or no data
            results.append({
                'driver': driver_info_map[drv_num],
                'position': 99,
                'drspit': {'drsStatus': 0, 'pitStatus': 0},
                'status': {'retired': False, 'stopped': False, 'danger': False, 'knockedOut': False},
                'tire': {'compound': 'UNKNOWN', 'laps': 0},
                'Gap': {'toLeader': '-- ---', 'toFront': '-- ---'},
                'lapTime': {
                    'lastLap': {'lapTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                    'bestLap': {'lapTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                },
                'sectors': [
                    {'sectorLast': {'sectorTime': '-- ---', 'previousSectorTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                     'sectorBest': {'sectorTime': '-- ---', 'previousSectorTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                     'segments': []},
                ] * 3,
                '_lapEndSeconds': None,
            })
            continue

        drv_segs = current_segments.get(drv_num, {0: {}, 1: {}, 2: {}})
        for s_idx in range(3):
            state['sectors'][s_idx]['segments'] = _dict_to_array(drv_segs[s_idx])

        if state['lapNumber'] > current_lap:
            current_lap = state['lapNumber']

        # Determine pit status
        pit_status = 0
        if state['pitIn']:
            pit_status = 1
        elif state['pitOut']:
            pit_status = 2

        # Check if driver is retired (no more laps after current)
        is_retired = False
        is_stopped = False
        all_drv_states = driver_lap_states.get(drv_num, [])
        if all_drv_states:
            last_state = all_drv_states[-1]
            if (last_state['lapEndSeconds'] is not None and
                last_state['lapEndSeconds'] <= current_session_time and
                last_state['lapNumber'] < total_laps):
                # Driver's last lap ended before the race ended
                # Check results for retired status
                try:
                    drv_result = session.results.loc[drv_num]
                    status = drv_result.get('Status', '')
                    if status and 'Finished' not in str(status) and '+' not in str(status):
                        is_retired = True
                except Exception:
                    pass

        result = {
            'driver': driver_info_map[drv_num],
            'position': state['position'],
            'drspit': {'drsStatus': 0, 'pitStatus': pit_status},
            'status': {'retired': is_retired, 'stopped': is_stopped, 'danger': False, 'knockedOut': False},
            'tire': {'compound': state['compound'], 'laps': state['tyreLife']},
            'Gap': {'toLeader': '-- ---', 'toFront': '-- ---'},
            'lapTime': state['lapTime'],
            'sectors': state['sectors'],
            '_lapEndSeconds': state['lapEndSeconds'],
        }
        results.append(result)

    # Compute gaps
    results = _compute_gap_to_leader(results)

    # Remove internal field and sort by position
    for r in results:
        r.pop('_lapEndSeconds', None)
    results.sort(key=lambda x: x['position'])

    # ─── Weather ───
    weather = _get_current_value(weather_timeline, current_session_time)
    if weather is None:
        weather = {
            'airTemp': 0, 'humidity': 0, 'pressure': 0,
            'rainfall': False, 'trackTemp': 0, 'windDirection': 0, 'windSpeed': 0,
        }

    # ─── Track Status ───
    track_status = _get_current_value(track_status_timeline, current_session_time)
    if track_status is None:
        track_status = {'status': 1, 'message': 'AllClear'}

    # ─── Clock (remaining time estimate) ───
    # Estimate remaining based on total laps and current lap
    remaining_laps = max(0, total_laps - current_lap)
    # Rough estimate: ~100s per lap
    remaining_estimate = remaining_laps * 100
    clock = {
        'remaining': remaining_estimate,
        'extrapolating': False,
    }

    # ─── Race Control Messages ───
    race_control_messages = _get_accumulated_messages(rcm_timeline, current_session_time)

    # ─── Other (lap count for race) ───
    other = {
        'currentLap': current_lap,
        'totalLaps': total_laps,
    }

    snapshot = {
        'grandPrixName': grand_prix_name,
        'session': session_name,
        'country': country,
        'circuit': circuit,
        'results': results,
        'weather': weather,
        'clock': clock,
        'raceControlMessages': race_control_messages,
        'teamRadio': [],  # Not available from fastf1 in this version
        'trackStatus': track_status,
        'other': other,
    }

    return snapshot
