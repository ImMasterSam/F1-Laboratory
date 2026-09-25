import { useEffect, useRef, useState } from "react"
import Dashboard from "../Component/LiveTiming/Dashboard"
import type { ConnectionState, dashData_type } from "../Type/Dashtypes"
import Map from "../Component/LiveTiming/Map";
import RaceControl from "../Component/LiveTiming/RaceControl";
import Radio from "../Component/LiveTiming/Radio";
import "../CSS/Page.css";
import '../CSS/Dashboard.css'
import '../CSS/DashInfo.css'
import Weather from "../Component/LiveTiming/Weather";


function LiveTimingPage() {

  const [data, setData] = useState<dashData_type | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    isConnected: false,
    lastDataTime: 0,
    reconnectAttempts: 0,
    error: null
  })
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const maxReconnectAttempts = 20
  const baseRetryDelay = 1000 // 1秒

  const cleanUpStream = () => {
    if (eventSourceRef.current) {
      console.log('[DEBUG] Close EventSource')
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
  }

   const scheduleReconnect = () => {
    if (retryTimeoutRef.current) {
      return // 已經有重連計劃
    }
    
    setConnectionState((prev) => {
      const nextAttempts = prev.reconnectAttempts + 1
      if (nextAttempts > maxReconnectAttempts) {
        window.alert("Reach maximum reconnect attempts, stop reconnecting\nConnection failed. Please refresh the page :(");
        console.error('[ERROR] Reach maximum reconnect attempts, stop reconnecting')
        return {
          ...prev,
          error: 'Connection failed. Please refresh the page :('
        }
      }
      const delay = baseRetryDelay
      console.log(`[INFO] Reconnect in ${delay}ms (${nextAttempts} Attempts)`)
      retryTimeoutRef.current = setTimeout(() => {
        retryTimeoutRef.current = null
        connectStream()
      }, delay)
      return {
        ...prev,
        reconnectAttempts: nextAttempts
      }
    })
  }

  const connectStream = () => {

    cleanUpStream()

    // const url = 'http://127.0.0.1:5000/stream/live'
    const url = 'https://f1lab-api.com/stream/live'
    console.log(`[INFO] Trying to connect to ${url}`)

    let eventSource = new EventSource(url)
    eventSourceRef.current = eventSource

    const connectionTimeout = setTimeout(() => {
      if (eventSource.readyState === EventSource.CONNECTING) {
        console.log('[WARNING] Connection Timeout')
        eventSource.close()
        scheduleReconnect()
      }
    }, 2 * baseRetryDelay) // 2s timeout

    eventSource.onopen = () => {
      console.log('[INFO] Connection opened');
      clearTimeout(connectionTimeout)
      setConnectionState((prev) => ({
        ...prev,
        isConnected: true,
        reconnectAttempts: 0,
        error: null
      }))

      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current)
        retryTimeoutRef.current = null
      }
    }

    eventSource.onmessage = (mes) => {
      //console.log(JSON.parse(mes.data).results[0]);
      try {
        const content: dashData_type = JSON.parse(mes.data)
        console.log('[DEBUG] Data Received:', content)
        setData(content)
        
        setConnectionState((prev) => ({
          ...prev,
          lastDataTime: Date.now(),
          error: null
        }))

        if (content.error) {
          console.error('[ERROR] Srver Error:', content.error)
          setConnectionState((prev) => ({
            ...prev,
            error: content.error ?? null
          }))
          scheduleReconnect()
        }

        if (content.type === 'connected') {
          console.log('[INFO] Server Connected')
          return
        }
        else{
          setData(content)
        }
      }
      catch (error) {
        console.error('[ERROR] Error occurs when handling message:', error, mes.data)
      }

    }

    eventSource.onerror = (error) => {

      console.error('SSE error:', error);
      setConnectionState((prev) => ({
        ...prev,
        isConnected: false,
        error: 'Connection error'
      }))

      // Check connection status
      if (eventSource.readyState === EventSource.CLOSED) {
        console.log('[INFO] connection closed，start reconnecting')
        scheduleReconnect()
      }
      else if (eventSource.readyState === EventSource.CONNECTING) {
        console.log('[INFO] trying to reconnect...')
        scheduleReconnect()
      }
    }
  }

  useEffect(() => {
    // console.log('[INFO] Loading components in Live Timing Page');
    // connectStream();

    // // Internet Status Monitoring
    // const handleOnline = () => {
    //   console.log('[INFO] Internet Recovered')
    //   connectStream()
    // }
    
    // const handleOffline = () => {
    //   console.log('[INFO] Internet Disconnected')
    //   setConnectionState(prev => ({
    //     ...prev,
    //     isConnected: false,
    //     error: 'Internet is Disconnected'
    //   }))
    // }

    // window.addEventListener('online', handleOnline)
    // window.addEventListener('offline', handleOffline)

    // return () => {
    //   console.log('[INFO] Unloading components in Live Timing Page, and cleaning up');
    //   cleanUpStream()
    //   window.removeEventListener('online', handleOnline)
    //   window.removeEventListener('offline', handleOffline)
    // }
  }, [])

  return <div className="live-timing">
    {data?.grandPrixName 
    ? <div className="dash-container">
      <Dashboard data={data} connectionState={connectionState} />
      <div className="dash-info">
        <div className="map-weather">
          {data.circuit && <Map circuit={data.circuit}/>}
          {data?.weather && <Weather weather={data?.weather}/>}
        </div>
        <div className='message-info'>
          {data.raceControlMessages && <RaceControl raceControlMessages={data.raceControlMessages} />}
          {data.teamRadio.length ? <Radio teamRadio={data.teamRadio} /> : <></>}
        </div>
      </div>
    </div>
    : <div className="connecting">
        <h2>Currently Unavailable</h2>
        <p>( Due to F1 new live timing policy )</p>
      </div>}
  </div>
}

export default LiveTimingPage