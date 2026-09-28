export type corner_type = {
  x: number;
  y: number;
  angle: number;
  number: number;
}

export type driverPos_type = {
  driver: driver_type;
  position: {
    x: number;
    y: number;
  };
}

export type circuit_type = {
  trackName: string;
  corners: corner_type[];
  trackPath: [number, number][];
  driverPos: driverPos_type[];
  rotation: number;
}

export type driver_type = {
  driverNumber: number;
  driverFullName: string;
  driverAbbreviation: string;
  driverTeamColor: string;
}

export type drspitInfo_type = {
  drsStatus: number;
  pitStatus: number;
}

export type statusInfo_type = {
  retired: boolean;
  stopped: boolean;
  danger: boolean;
  knockedOut: boolean;
}

export type tireInfo_type = {
  compound: string;
  laps: number;
}

export type gapInfo_type = {
  toLeader: string;
  toFront: number;
}

export type lapStatus_type = {
  lapTime: string;
  overallFastest: boolean;
  personalFastest: boolean;
}

export type lapInfo_type = {
  lastLap: lapStatus_type;
  bestLap: lapStatus_type;
}

export type sectorStatus_type = {
  sectorTime: string;
  previousSectorTime: string;
  overallFastest: boolean;
  personalFastest: boolean;
}

export type sectorInfo_type = {
  sectorLast: sectorStatus_type;
  sectorBest: sectorStatus_type;
  segments: number[];
}

export type result_type = {
  driver: driver_type;
  position: number;
  drspit: drspitInfo_type;
  status: statusInfo_type;
  tire: tireInfo_type;
  Gap: gapInfo_type;
  lapTime: lapInfo_type;
  sectors: sectorInfo_type[];
}

export type weather_type = {
  airTemp: number;
  humidity: number;
  pressure: number;
  rainfall: boolean;
  trackTemp: number;
  windDirection: number;
  windSpeed: number;
}

export type trackStatus_type = {
  status: number;
  message: string;
}

export type clock_type = {
  remaining: number;
  extrapolating: boolean;
}

export type quali_type = {
  entries: number[];
}

export type race_type = {
  currentLap: number;
  totalLaps: number;
}

export type raceControlMessages_type = {
  Utc: string;
  Lap: number;
  Category: string;
  Flag: string | null;
  Scope: string | null;
  Message: string;
}

export type teamRadio_type = {
  Utc: string;
  Path: string;
  driver: driver_type;
}

export type dashData_type = {
  grandPrixName: string;
  session: string;
  country: string;
  circuit: circuit_type;
  results: result_type[];
  weather: weather_type;
  clock: clock_type;
  raceControlMessages: raceControlMessages_type[];
  teamRadio: teamRadio_type[];
  trackStatus: trackStatus_type;
  other?: quali_type | race_type;

  type?: 'connected' | 'data';
  timestamp?: number;
  error?: string;
}