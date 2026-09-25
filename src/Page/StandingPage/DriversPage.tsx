import { useEffect, useState } from "react"
import PointsEvolution from "../../Component/Standing/charts/PointsEvolution"
import DriverStanding from "../../Component/Standing/DriverStanding"
import type { driverStanding_type } from "../../Type/StandingTypes"
import { fetchScheduleList, getDriverStanding, fetchYearList } from "../../Lib/Fetch"
import type { race_type } from "../../Type/RaceTypes"
import type { yearlist_type } from "../../Type/Scheduletypes"
import RankEvolution from "../../Component/Standing/charts/RankEvolution"
import '../../CSS/Standings.css'

function DriversPage() {

  const [driverStanding, setDriverStanding] = useState<Array<driverStanding_type>>([])
  const [schedule, setSchedule] = useState<Array<race_type>>([])
  const [errMessage, setErrMessage] = useState<string>('')
  const [yearList, setYearList] = useState<Array<yearlist_type>>([])
  const [year, setYear] = useState<number>(new Date().getFullYear())

  useEffect(() => {
    fetchYearList().then((data) => {
      // Sort the list descending so latest year is on top
      data.sort((a, b) => b.season - a.season)
      setYearList(data)
    }).catch((error) => { setErrMessage(String(error)) })
  }, [])

  useEffect(() => {
    getDriverStanding(year).then((data) => {
      setDriverStanding(data)
    }).catch((error) => { setErrMessage(String(error)) })
    fetchScheduleList(year).then((data) => {
      setSchedule(data)
    }).catch((error) => { setErrMessage(String(error)) })
  }, [year])

  return (
    <div className='standing-page'>
      <div className="standing-title-container">
        <select onChange={(e) => setYear(parseInt(e.target.value))} value={year}>
          {yearList.length > 0 ? yearList.map((Year) => {
            return <option key={Year.season} value={Year.season}>{Year.season}</option>
          })
          : <option>{year}</option>}
        </select>
        <h2 className="standing-title">Driver Championship Standings</h2>
      </div>
      {errMessage ? <h3>{errMessage}</h3>
        :
        <div className="standing-container">
          <DriverStanding driverStanding={driverStanding} />
          <div className="standing-chart">
            <PointsEvolution type='driver' year={year} schedule={schedule} standing={driverStanding} />
            <RankEvolution type='driver' year={year} schedule={schedule} standing={driverStanding} />
          </div>
        </div>}

    </div>
  )
}

export default DriversPage