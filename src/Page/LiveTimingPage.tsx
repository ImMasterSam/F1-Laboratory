import { useCallback, useEffect, useRef, useState } from "react"
import Dashboard from "../Component/LiveTiming/Dashboard"
import type { dashData_type } from "../Type/Dashtypes"
import Map from "../Component/LiveTiming/Map";
import RaceControl from "../Component/LiveTiming/RaceControl";
import Radio from "../Component/LiveTiming/Radio";
import "../CSS/Page.css";
import '../CSS/Dashboard.css'
import '../CSS/DashInfo.css'
import Weather from "../Component/LiveTiming/Weather";
import ReplayControls from "../Component/LiveTiming/ReplayControls";

type ReplayMetadata = {
  grandPrixName: string;
  session: string;
  country: string;
  totalDuration: number;
  totalLaps: number;
  year: number;
  round: number;
}

type ReplayData = {
  metadata: ReplayMetadata;
  snapshots: dashData_type[];
}

type LoadingState = 'idle' | 'loading' | 'loaded' | 'error';

function LiveTimingPage() {

  const [data, setData] = useState<dashData_type | null>(null)
  const [snapshots, setSnapshots] = useState<dashData_type[]>([])
  const [metadata, setMetadata] = useState<ReplayMetadata | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loadingState, setLoadingState] = useState<LoadingState>('idle')
  const [loadingError, setLoadingError] = useState<string | null>(null)

  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Format seconds to MM:SS
  const formatTime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = seconds % 60
    if (h > 0) {
      return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }

  // Fetch replay data
  const loadReplayData = useCallback(async () => {
    setLoadingState('loading')
    setLoadingError(null)

    try {
      // 這裡先寫死 127.0.0.1 供本地測試
      const url = 'http://127.0.0.1:5000/api/replay'
      console.log(`[INFO] Fetching replay data from ${url}`)

      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const replayData: ReplayData = await response.json()
      console.log(`[INFO] Replay data loaded: ${replayData.snapshots.length} snapshots`)
      console.log(`[INFO] Metadata:`, replayData.metadata)

      setSnapshots(replayData.snapshots)
      setMetadata(replayData.metadata)
      setCurrentIndex(0)
      setData(replayData.snapshots[0] || null)
      setLoadingState('loaded')
    } catch (error) {
      console.error('[ERROR] Failed to load replay data:', error)
      setLoadingError(error instanceof Error ? error.message : 'Unknown error')
      setLoadingState('error')
    }
  }, [])

  // Playback control
  useEffect(() => {
    if (isPlaying && snapshots.length > 0) {
      playIntervalRef.current = setInterval(() => {
        setCurrentIndex(prev => {
          const next = prev + 1
          if (next >= snapshots.length) {
            setIsPlaying(false)
            return prev
          }
          return next
        })
      }, 1000) // 1 second per snapshot (1x speed)
    }

    return () => {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current)
        playIntervalRef.current = null
      }
    }
  }, [isPlaying, snapshots.length])

  // Update displayed data when currentIndex changes
  useEffect(() => {
    if (snapshots.length > 0 && currentIndex < snapshots.length) {
      setData(snapshots[currentIndex])
    }
  }, [currentIndex, snapshots])

  // Auto-load replay data on mount
  useEffect(() => {
    loadReplayData()
  }, [loadReplayData])

  // Handle play/pause toggle
  const handlePlayPause = () => {
    if (currentIndex >= snapshots.length - 1) {
      // If at the end, restart
      setCurrentIndex(0)
      setIsPlaying(true)
    } else {
      setIsPlaying(!isPlaying)
    }
  }

  // Handle seek (slider change)
  const handleSeek = (index: number) => {
    setCurrentIndex(index)
    // Don't auto-pause on seek - let user control play state
  }

  return <div className="live-timing">
    {loadingState === 'loading' && (
      <div className="connecting">
        <div className="loading-spinner"></div>
        <h2>Loading Replay Data...</h2>
        <p>Fetching historical race data from server, this may take a moment.</p>
      </div>
    )}

    {loadingState === 'error' && (
      <div className="connecting">
        <h2>Failed to Load</h2>
        <p>{loadingError}</p>
        <button className="retry-btn" onClick={loadReplayData}>Retry</button>
      </div>
    )}

    {loadingState === 'loaded' && data?.grandPrixName && (
      <div className="dash-container">
        <Dashboard data={data} />
        <div className="dash-info">
          {snapshots.length > 0 && (
            <ReplayControls
              isPlaying={isPlaying}
              currentIndex={currentIndex}
              totalSnapshots={snapshots.length}
              onPlayPause={handlePlayPause}
              onSeek={handleSeek}
              formatTime={formatTime}
            />
          )}
          <div className="map-weather">
            {data.circuit && <Map circuit={data.circuit} />}
            {data?.weather && <Weather weather={data?.weather} />}
          </div>
          <div className='message-info'>
            {data.raceControlMessages && <RaceControl raceControlMessages={data.raceControlMessages} />}
            {data.teamRadio.length ? <Radio teamRadio={data.teamRadio} /> : <></>}
          </div>
        </div>
      </div>
    )}

  </div>
}

export default LiveTimingPage