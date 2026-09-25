import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getConstructorPointsEvolution, getDriverPointsEvolution } from "../../../Lib/standingData";
import type { pointsEvolution_type, driverStanding_type, constructorStanding_type } from "../../../Type/StandingTypes";
import { team_theme } from "../../../Lib/TeamTheme";
import type { race_type } from "../../../Type/RaceTypes";

type Props = {
  type?: 'driver' | 'constructor';
  year: number;
  schedule: race_type[]
  standing: driverStanding_type[] | constructorStanding_type[];
}

type PointsCustomTooltipProps = {
  active?: boolean;
  payload?: readonly any[];
  label?: string | number;
  schedule: race_type[];
};

function PointsEvolutionTooltip({ active, payload, label, schedule }: PointsCustomTooltipProps) {
  if (active && payload && payload.length) {

    // Grand Prix Name
    const currentRace = schedule.find(race => parseInt(String(race.round)) === parseInt(String(label) || '0'));
    const raceName = currentRace ? currentRace.raceName : `Round ${label}`;

    // Sort Data
    const sortedPayload = [...payload].sort((a, b) => b.value - a.value);

    return (
      <div className="custom-tooltip">

        {/* 標題與分站名稱 */}
        <div className="tooltip-header">
          <p className="tooltip-race-name">{raceName}</p>
          <p className="tooltip-round-info">Round {label}</p>
        </div>

        {/* 列表內容 */}
        <div className="tooltip-list">
          {sortedPayload.map((entry: any) => (
            <div key={entry.name} className="tooltip-item">
              <div className="tooltip-driver-info">
                <span
                  className="tooltip-color-dot"
                  style={{ backgroundColor: entry.color }}
                ></span>
                <span className="tooltip-driver-name">{entry.name}</span>
              </div>
              <span className="tooltip-points">{entry.value} pts</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return null;
}

function PointsEvolution({ type, year, schedule, standing }: Props) {

  const [evolutionData, setEvolutionData] = useState<pointsEvolution_type[]>([]);
  const [dataKeys, setDataKeys] = useState<string[]>([]);

  useEffect(() => {

    setEvolutionData([])

    const fetchData = async () => {
      let data: pointsEvolution_type[] = [];

      if (type === 'driver') {
        data = await getDriverPointsEvolution(year);
      } else {
        data = await getConstructorPointsEvolution(year);
      }

      setEvolutionData(data);
      console.log(`${type} Points Evolution Data:`, data);

      if (data.length > 0) {
        const keys = Object.keys(data[data.length - 1])
        // 過濾掉非參賽者資料的 key
        const validKeys = keys.filter((key) => key !== 'round' && key !== 'name');
        setDataKeys(validKeys)
        console.log(`${type} Points Evolution Data Key:`, validKeys);
      }
    };

    fetchData();
  }, [year, type])

  return (
    <div className="standing-chart-container">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={evolutionData} margin={{ top: 10, right: 20, bottom: 20, left: 20 }}>

          <CartesianGrid strokeDasharray="3 3" stroke="#444" opacity={0.9} />

          <XAxis
            dataKey="round"
            label={{ value: 'Round', fontWeight: 'bold', position: 'insideBottom', offset: -10, fill: '#fff' }}
            stroke="white"
          />
          <YAxis
            domain={[0, 'max']}
            label={{ value: 'Points', fontWeight: 'bold', angle: -90, position: 'insideLeft', fill: '#fff' }}
            stroke="white"
          />
          <Tooltip
            content={(props) => <PointsEvolutionTooltip {...props} schedule={schedule} />}
            cursor={{ stroke: '#fff', strokeWidth: 1, strokeDasharray: "4 4" }}
            wrapperStyle={{ zIndex: 1000 }}
          />
          {dataKeys.map((key) => {

            let teamColor: string = "#888";
            let displayName: string = key;

            if (type === 'driver') {
              const driver = (standing as driverStanding_type[]).find((driverData) => {
                let driverKey = '';
                if (driverData.Driver.code)
                  driverKey = driverData.Driver.code;
                else
                  driverKey = driverData.Driver.familyName.slice(0, 3).toUpperCase();
                return driverKey === key
              })
              if (!driver) return null;

              teamColor = team_theme[driver.Constructors?.[driver.Constructors.length - 1].constructorId];
              displayName = `${driver.Driver.givenName} ${driver.Driver.familyName}`;

            }
            else if (type === 'constructor') {
              const constructor = (standing as constructorStanding_type[]).find((constructorData) => {
                return constructorData.Constructor.constructorId == key;
              })
              if (!constructor) return null;
              
              teamColor = team_theme[constructor.Constructor.constructorId] || "#888";
              displayName = constructor.Constructor.name;
            }

            return (
              <Line
                type="monotone"
                key={key}
                name={displayName}
                dataKey={key}
                stroke={teamColor}
                strokeWidth={3}
                dot={{ r: 3, strokeWidth: 0, fill: teamColor }}
                activeDot={{ r: 6, stroke: '#fff', strokeWidth: 2 }}
              />
            )
          })}

        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PointsEvolution