import ReactCountryFlag from "react-country-flag";
import DashboardRow from "./DashComponent/DashboardRow";
import type { dashData_type } from "../../Type/Dashtypes"
import { Country } from "../../Lib/CountryCode";
import TrackStatus from "./DashComponent/DashHeader/TrackStatus";
import CountDown from "./DashComponent/DashHeader/CountDown";
import { useState } from "react";

type dash_Props = {
  data: dashData_type | null;
}

type dashHeader_Props = {
  data: dashData_type
}

function DashboardHeader({ data }: dashHeader_Props) {
  return <div className="dash-header">
    <div className="grandPrix-title">
      <ReactCountryFlag countryCode={Country[data.country]}
        aria-label={data.country}
        style={{ scale: 2 }} svg />
      <h2>{data.grandPrixName} - {data.session}</h2>
    </div>
    {data?.clock && <CountDown clock={data.clock} />}
    {data?.other && 'currentLap' in data.other && 'totalLaps' in data.other && (
      <h3>{`Lap ${data.other.currentLap} / ${data.other.totalLaps}`}</h3>
    )}
    {data?.trackStatus && <TrackStatus trackStatus={data.trackStatus} />}
  </div>
}

function Dashboard({ data }: dash_Props) {

  const [intervalTop, setIntervalTop] = useState<boolean>(true)

  const handleGapTop = () => {
    setIntervalTop(!intervalTop)
  }

  return <div className="dashboard">
    {data?.grandPrixName && <DashboardHeader data={data} />}
    <div className="drivers-table">
      {data?.results ? data.results.map((result) => {
        return <DashboardRow result={result} intervalTop={intervalTop} handleGapTop={handleGapTop} key={result.driver.driverNumber} />
      }) : <p>Loading Data ...</p>}
    </div>
  </div>
}

export default Dashboard