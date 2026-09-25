import PointsEvolution from "../../Component/Standing/charts/PointsEvolution"
import ConstructorStanding from "../../Component/Standing/ConstructorStanding"
import '../../CSS/Standings.css'
import type { constructorStanding_type } from "../../Type/StandingTypes"
import { useEffect, useState } from "react"
import type { race_type } from "../../Type/RaceTypes"
import RankEvolution from "../../Component/Standing/charts/RankEvolution"
import { fetchScheduleList, getConstructorStanding, fetchYearList } from "../../Lib/Fetch"
import type { yearlist_type } from "../../Type/Scheduletypes"

function ConstructorsPage() {

  const [constructorStanding, setConstructorStanding] = useState<Array<constructorStanding_type>>([])
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
    getConstructorStanding(year).then((data) => {
      console.log('constructor standings: ', data)
      setConstructorStanding(data)
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
        <h2 className="standing-title">Constructor Championship Standings</h2>
      </div>
      {errMessage ? <h3>{errMessage}</h3>
        :
        <div className="standing-container">
          <ConstructorStanding constructorStanding={constructorStanding} />
          <div className="standing-chart">
            <PointsEvolution type='constructor' year={year} schedule={schedule} standing={constructorStanding} />
            <RankEvolution type='constructor' year={year} schedule={schedule} standing={constructorStanding} />
          </div>
        </div>}

    </div>
  )
}

export default ConstructorsPage