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


def _build_timing_app_timeline(session) -> list:
    from fastf1._api import fetch_page, parse
    import pandas as pd
    import copy

    try:
        page_content = fetch_page(session.api_path, 'timing_data')
        if not page_content:
            return []
        records = parse(page_content)
    except Exception as e:
        logger.error(f"Failed to fetch timing_data: {e}")
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
                    state[drv] = {
                        'segments': {0: {}, 1: {}, 2: {}},
                        'gap': '-- ---',
                        'interval': '-- ---'
                    }

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
                                    state[drv]['segments'][s_idx][int(seg_idx)] = seg_data['Status']
                                    updated = True

                if 'GapToLeader' in drv_data:
                    gap_val = drv_data['GapToLeader']
                    if gap_val is None:
                        state[drv]['gap'] = ''
                    else:
                        state[drv]['gap'] = str(gap_val)
                    updated = True

                if 'IntervalToPositionAhead' in drv_data:
                    int_val = drv_data['IntervalToPositionAhead']
                    if int_val is None:
                        pass
                    elif isinstance(int_val, dict):
                        if 'Value' in int_val:
                            state[drv]['interval'] = str(int_val['Value'])
                    else:
                        state[drv]['interval'] = str(int_val)
                    updated = True

        if updated:
            timeline.append({
                'time': t,
                'data': copy.deepcopy(state)
            })

    return timeline


def _build_grid_positions(session) -> dict:
    """Build grid position map { driver_number_str: grid_position }.
    Uses session.results GridPosition if available, otherwise falls back to
    qualifying results or driver order."""
    grid = {}
    try:
        results = session.results
        for drv_num_str in session.drivers:
            try:
                drv_result = results.loc[drv_num_str]
                gp = drv_result.get('GridPosition', None)
                if pd.notna(gp) and int(gp) > 0:
                    grid[drv_num_str] = int(gp)
                else:
                    grid[drv_num_str] = 99
            except (KeyError, TypeError):
                grid[drv_num_str] = 99
    except Exception as e:
        logger.warning(f"Could not build grid positions: {e}")
        for i, drv_num_str in enumerate(session.drivers, 1):
            grid[drv_num_str] = i
    return grid


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

    # ─── Build grid positions (starting order) ───
    grid_positions = _build_grid_positions(session)

    # ─── Build weather timeline ───
    weather_timeline = _build_weather_timeline(session)

    # ─── Build track status timeline ───
    track_status_timeline = _build_track_status_timeline(session)

    # ─── Build race control messages timeline ───
    rcm_timeline = _build_rcm_timeline(session)
    timing_app_timeline = _build_timing_app_timeline(session)

    # ─── Compute default segment counts per sector ───
    # Used to fill empty segments with status=0 so frontend elements don't disappear
    default_segment_counts = {0: 0, 1: 0, 2: 0}
    for entry in timing_app_timeline:
        for drv_num, drv_data in entry['data'].items():
            drv_segs = drv_data.get('segments', {})
            for s_idx in range(3):
                if s_idx in drv_segs and drv_segs[s_idx]:
                    count = max(drv_segs[s_idx].keys()) + 1
                    if count > default_segment_counts[s_idx]:
                        default_segment_counts[s_idx] = count
        if all(v > 0 for v in default_segment_counts.values()):
            break  # Found counts for all 3 sectors

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
            timing_app_timeline=timing_app_timeline,
            session=session,
            grid_positions=grid_positions,
            default_segment_counts=default_segment_counts,
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
    Each entry includes the session time when the lap started and ended.
    """
    laps = session.laps
    states = {}

    # Pre-compute session start time for lap start estimation
    session_start_seconds = session.session_start_time.total_seconds()

    for drv_num_str in session.drivers:
        drv_laps = laps.pick_drivers(drv_num_str).sort_values('LapNumber')
        driver_states = []
        personal_best_lap = pd.NaT
        personal_best_s1 = pd.NaT
        personal_best_s2 = pd.NaT
        personal_best_s3 = pd.NaT

        prev_lap_end_seconds = None

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

            # Determine when this lap started
            # For the first lap, use session start time or LapStartTime if available
            lap_start_time = lap.get('LapStartTime', pd.NaT)
            if pd.notna(lap_start_time):
                lap_start_seconds = lap_start_time.total_seconds()
            elif prev_lap_end_seconds is not None:
                lap_start_seconds = prev_lap_end_seconds
            else:
                # First lap — use session start time as approximation
                lap_start_seconds = session_start_seconds

            # Sector session times (when each sector was completed)
            s1_end = lap['Sector1SessionTime']
            s2_end = lap['Sector2SessionTime']
            s3_end = lap['Sector3SessionTime']

            state = {
                'lapNumber': int(lap['LapNumber']) if pd.notna(lap['LapNumber']) else 0,
                'position': int(lap['Position']) if pd.notna(lap['Position']) else 99,
                'lapStartSeconds': lap_start_seconds,
                'lapEndSeconds': lap_end_seconds,
                'sectorEndSeconds': [
                    s1_end.total_seconds() if pd.notna(s1_end) else None,
                    s2_end.total_seconds() if pd.notna(s2_end) else None,
                    s3_end.total_seconds() if pd.notna(s3_end) else None,
                ],
                'lapTime': {
                    'lastLap': {
                        'lapTime': _format_timedelta(lap_time),
                        'personalFastest': is_pb_lap,
                        'value': lap_time.total_seconds() if pd.notna(lap_time) else None,
                    },
                    'bestLap': {
                        'lapTime': _format_timedelta(personal_best_lap),
                        'personalFastest': True,
                        'value': personal_best_lap.total_seconds() if pd.notna(personal_best_lap) else None,
                    },
                },
                'sectors': [
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s1_time),
                            'previousSectorTime': '-- ---',
                            'personalFastest': is_pb_s1,
                            'value': s1_time.total_seconds() if pd.notna(s1_time) else None,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s1),
                            'previousSectorTime': '-- ---',
                            'personalFastest': True,
                            'value': personal_best_s1.total_seconds() if pd.notna(personal_best_s1) else None,
                        },
                        'segments': [],
                    },
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s2_time),
                            'previousSectorTime': '-- ---',
                            'personalFastest': is_pb_s2,
                            'value': s2_time.total_seconds() if pd.notna(s2_time) else None,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s2),
                            'previousSectorTime': '-- ---',
                            'personalFastest': True,
                            'value': personal_best_s2.total_seconds() if pd.notna(personal_best_s2) else None,
                        },
                        'segments': [],
                    },
                    {
                        'sectorLast': {
                            'sectorTime': _format_timedelta(s3_time),
                            'previousSectorTime': '-- ---',
                            'personalFastest': is_pb_s3,
                            'value': s3_time.total_seconds() if pd.notna(s3_time) else None,
                        },
                        'sectorBest': {
                            'sectorTime': _format_timedelta(personal_best_s3),
                            'previousSectorTime': '-- ---',
                            'personalFastest': True,
                            'value': personal_best_s3.total_seconds() if pd.notna(personal_best_s3) else None,
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
            prev_lap_end_seconds = lap_end_seconds

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


def _get_driver_state_at_time(driver_states: list, current_session_time: float) -> tuple[Optional[dict], bool, Optional[dict]]:
    """Get the latest lap state for a driver at the given session time.

    Returns (state, is_mid_lap, last_completed):
      - state: the best matching lap state, or None if no data
      - is_mid_lap: True if the driver is currently mid-lap (lap started but not finished)
      - last_completed: the last fully completed lap state (for gap computation during mid-lap)
    """
    last_completed = None
    current_in_progress = None

    for state in driver_states:
        lap_start = state.get('lapStartSeconds')
        lap_end = state.get('lapEndSeconds')

        if lap_end is not None and lap_end <= current_session_time:
            # This lap is fully completed
            last_completed = state
        elif lap_start is not None and lap_start <= current_session_time:
            # This lap has started but hasn't ended yet — we're mid-lap
            current_in_progress = state
            break  # States are sorted by lap number, so the first in-progress is current
        elif lap_end is None and lap_start is None:
            # Fallback: no timing data at all, use as initial state
            if last_completed is None:
                last_completed = state

    if current_in_progress is not None:
        return current_in_progress, True, last_completed
    return last_completed, False, last_completed





def _build_snapshot(t: int, current_session_time: float,
                    grand_prix_name: str, session_name: str, country: str,
                    total_laps: int, circuit_data: dict,
                    pos_data_resampled: dict, driver_lap_states: dict,
                    driver_info_map: dict, weather_timeline: list,
                    track_status_timeline: list, rcm_timeline: list,
                    timing_app_timeline: list, session,
                    grid_positions: dict = None,
                    default_segment_counts: dict = None) -> dict:
    """Build a single snapshot at time t (seconds from race start)."""

    if grid_positions is None:
        grid_positions = {}
    if default_segment_counts is None:
        default_segment_counts = {0: 0, 1: 0, 2: 0}

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

    # ─── Timing App Data (Segments, Gap, Interval) ───
    current_timing_app = _get_current_value(timing_app_timeline, current_session_time) or {}

    # ─── Determine overall bests up to current_session_time ───
    overall_best_lap_val = None
    overall_best_s1_val = None
    overall_best_s2_val = None
    overall_best_s3_val = None

    drv_states_at_time = {}
    for drv_num in driver_info_map.keys():
        drv_states = driver_lap_states.get(drv_num, [])
        state, is_mid_lap, last_completed = _get_driver_state_at_time(drv_states, current_session_time)
        drv_states_at_time[drv_num] = (state, is_mid_lap, last_completed)

        if state is None:
            continue

        # Lap best
        lap_state = last_completed if is_mid_lap else state
        if lap_state:
            val = lap_state['lapTime']['bestLap'].get('value')
            if val is not None and (overall_best_lap_val is None or val < overall_best_lap_val):
                overall_best_lap_val = val

        # Sector 1
        s1_state = state if (state['sectorEndSeconds'][0] is not None and state['sectorEndSeconds'][0] <= current_session_time) else last_completed
        if s1_state:
            val = s1_state['sectors'][0]['sectorBest'].get('value')
            if val is not None and (overall_best_s1_val is None or val < overall_best_s1_val):
                overall_best_s1_val = val

        # Sector 2
        s2_state = state if (state['sectorEndSeconds'][1] is not None and state['sectorEndSeconds'][1] <= current_session_time) else last_completed
        if s2_state:
            val = s2_state['sectors'][1]['sectorBest'].get('value')
            if val is not None and (overall_best_s2_val is None or val < overall_best_s2_val):
                overall_best_s2_val = val

        # Sector 3
        s3_state = state if (state['sectorEndSeconds'][2] is not None and state['sectorEndSeconds'][2] <= current_session_time) else last_completed
        if s3_state:
            val = s3_state['sectors'][2]['sectorBest'].get('value')
            if val is not None and (overall_best_s3_val is None or val < overall_best_s3_val):
                overall_best_s3_val = val


    # ─── Driver results (position, lap time, tire, etc.) ───
    results = []
    current_lap = 0

    for drv_num in driver_info_map.keys():
        state, is_mid_lap, last_completed = drv_states_at_time[drv_num]

        if state is None:
            # Driver hasn't started yet — use grid position and first lap tire info
            grid_pos = grid_positions.get(drv_num, 99)
            first_compound = 'UNKNOWN'
            first_tyre_life = 0
            drv_states = driver_lap_states.get(drv_num, [])
            if drv_states:
                first_compound = drv_states[0].get('compound', 'UNKNOWN')
                first_tyre_life = drv_states[0].get('tyreLife', 0)

            # Use default segment counts to provide status=0 arrays
            default_sectors = []
            for s_idx in range(3):
                default_sectors.append({
                    'sectorLast': {'sectorTime': '-- ---', 'previousSectorTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                    'sectorBest': {'sectorTime': '-- ---', 'previousSectorTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                    'segments': [0] * default_segment_counts.get(s_idx, 0),
                })

            results.append({
                'driver': driver_info_map[drv_num],
                'position': grid_pos,
                'drspit': {'drsStatus': 0, 'pitStatus': 0},
                'status': {'retired': False, 'stopped': False, 'danger': False, 'knockedOut': False},
                'tire': {'compound': first_compound, 'laps': first_tyre_life},
                'Gap': {'toLeader': '+-.---', 'toFront': '+-.---'},
                'lapTime': {
                    'lastLap': {'lapTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                    'bestLap': {'lapTime': '-- ---', 'overallFastest': False, 'personalFastest': False},
                },
                'sectors': default_sectors,
            })
            continue

        drv_timing = current_timing_app.get(drv_num, {})
        drv_segs = drv_timing.get('segments', {0: {}, 1: {}, 2: {}})
        for s_idx in range(3):
            seg_array = _dict_to_array(drv_segs.get(s_idx, {}))
            # If no segment data yet, fill with status=0 using default counts
            if not seg_array and default_segment_counts.get(s_idx, 0) > 0:
                seg_array = [0] * default_segment_counts[s_idx]
            state['sectors'][s_idx]['segments'] = seg_array

        if state['lapNumber'] > current_lap:
            current_lap = state['lapNumber']

        # For mid-lap drivers on lap 1 that haven't had any completed lap yet,
        # use grid position for ranking
        position = state['position']
        if is_mid_lap and state['lapNumber'] <= 1:
            # Use grid position if the state position is invalid (99 or missing)
            if position == 99 or position == 0:
                position = grid_positions.get(drv_num, 99)

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

        # Build sector data: for mid-lap, show sector times as they become available
        sectors_data = []
        overall_best_s_vals = [overall_best_s1_val, overall_best_s2_val, overall_best_s3_val]
        for s_idx in range(3):
            sector = state['sectors'][s_idx]
            sector_end = state['sectorEndSeconds'][s_idx]

            if is_mid_lap and (sector_end is None or sector_end > current_session_time):
                # This sector hasn't been completed yet during mid-lap
                if last_completed:
                    s_data = {
                        'sectorLast': {
                            'sectorTime': '-- ---',
                            'previousSectorTime': '-- ---',
                            'personalFastest': False,
                        },
                        'sectorBest': dict(last_completed['sectors'][s_idx]['sectorBest']),
                        'segments': sector['segments'],
                    }
                else:
                    s_data = {
                        'sectorLast': {
                            'sectorTime': '-- ---',
                            'previousSectorTime': '-- ---',
                            'personalFastest': False,
                        },
                        'sectorBest': {
                            'sectorTime': '-- ---',
                            'previousSectorTime': '-- ---',
                            'personalFastest': False,
                        },
                        'segments': sector['segments'],
                    }
            else:
                s_data = {
                    'sectorLast': dict(sector['sectorLast']),
                    'sectorBest': dict(sector['sectorBest']),
                    'segments': sector['segments'],
                }

            # Compute overallFastest flag
            sl_val = s_data['sectorLast'].get('value')
            sb_val = s_data['sectorBest'].get('value')
            
            s_data['sectorLast']['overallFastest'] = (sl_val is not None and overall_best_s_vals[s_idx] is not None and sl_val == overall_best_s_vals[s_idx])
            s_data['sectorBest']['overallFastest'] = (sb_val is not None and overall_best_s_vals[s_idx] is not None and sb_val == overall_best_s_vals[s_idx])
            
            # clean up value key
            s_data['sectorLast'].pop('value', None)
            s_data['sectorBest'].pop('value', None)

            sectors_data.append(s_data)

        # For mid-lap, lap time hasn't been set yet
        if is_mid_lap:
            if last_completed:
                lap_time_data = {
                    'lastLap': dict(last_completed['lapTime']['lastLap']),
                    'bestLap': dict(last_completed['lapTime']['bestLap']),
                }
            else:
                lap_time_data = {
                    'lastLap': {
                        'lapTime': '-- ---',
                        'personalFastest': False,
                    },
                    'bestLap': {
                        'lapTime': '-- ---',
                        'personalFastest': False,
                    },
                }
        else:
            lap_time_data = {
                'lastLap': dict(state['lapTime']['lastLap']),
                'bestLap': dict(state['lapTime']['bestLap']),
            }

        # Compute overallFastest flag
        l_val = lap_time_data['lastLap'].get('value')
        lap_time_data['lastLap']['overallFastest'] = (l_val is not None and overall_best_lap_val is not None and l_val == overall_best_lap_val)

        b_val = lap_time_data['bestLap'].get('value')
        lap_time_data['bestLap']['overallFastest'] = (b_val is not None and overall_best_lap_val is not None and b_val == overall_best_lap_val)

        # clean up value key
        lap_time_data['lastLap'].pop('value', None)
        lap_time_data['bestLap'].pop('value', None)

        def _format_gap_val(val):
            import re
            if val is None or str(val).strip() in ('', '-- ---'):
                return '+-.---'
            val_str = str(val).strip()
            lap_match = re.match(r'^(\d+)\s*L$', val_str, re.IGNORECASE)
            if lap_match:
                laps = int(lap_match.group(1))
                return f"{laps} Lap" if laps == 1 else f"{laps} Laps"
            return val_str

        gap_to_leader = _format_gap_val(drv_timing.get('gap'))
        gap_to_front = _format_gap_val(drv_timing.get('interval'))

        result = {
            'driver': driver_info_map[drv_num],
            'position': position,
            'drspit': {'drsStatus': 0, 'pitStatus': pit_status},
            'status': {'retired': is_retired, 'stopped': is_stopped, 'danger': False, 'knockedOut': False},
            'tire': {'compound': state['compound'], 'laps': state['tyreLife']},
            'Gap': {'toLeader': gap_to_leader, 'toFront': gap_to_front},
            'lapTime': lap_time_data,
            'sectors': sectors_data,
        }
        results.append(result)

    # Sort by position
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
