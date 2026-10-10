import type { result_type } from "../../../Type/Dashtypes"
import Position from "./DashRowComponent/Position"
import Tire from "./DashRowComponent/Tire"
import Gap from "./DashRowComponent/Gap"
import LapTime from "./DashRowComponent/LapTime"
import Sector from "./DashRowComponent/Sector/Sector"
import DrsPit from "./DashRowComponent/DrsPit"
import type { MouseEventHandler } from "react"

type Props = {
  result: result_type;
  intervalTop: boolean;
  handleGapTop: MouseEventHandler;
}

const isOut = (result: result_type) => {
  if (result.status.retired || result.status.stopped || result.status.knockedOut)
    return true
  else
    return false
}

const isDanger = (result: result_type) => {
  if (result.status.danger)
    return true
  else
    return false
}

function DashboardRow({ result, intervalTop, handleGapTop }: Props) {

  return <div className={`dash-driver-row ${isOut(result) ? 'out' : ''} ${isDanger(result) ? 'danger' : ''}`} key={result.driver.driverNumber}>
    <Position driver={result.driver} position={result.position}/>
    <DrsPit drspit={result.drspit}/>
    <Tire tire={result.tire}/>
    <Gap gap={result.Gap} leading={result.position == 1} intervalTop={intervalTop} handleGapTop={handleGapTop}/>
    <LapTime lapTime={result.lapTime}/>
    {result.sectors?.map((sector, index) => {
      return <Sector sector={sector} key={index}/>
    })}
  </div>
}

export default DashboardRow