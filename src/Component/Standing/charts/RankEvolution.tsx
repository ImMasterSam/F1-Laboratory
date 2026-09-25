import { useEffect, useState } from "react";
import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { getConstructorPointsEvolution, getDriverPointsEvolution, getRankEvolution } from "../../../Lib/standingData";
import type { rankEvolution_type, driverStanding_type, pointsEvolution_type, constructorStanding_type } from "../../../Type/StandingTypes";
import { team_theme } from "../../../Lib/TeamTheme";
import type { race_type } from "../../../Type/RaceTypes";

type Props = {
  type?: 'driver' | 'constructor';
  year: number;
  schedule: race_type[]
  standing: driverStanding_type[] | constructorStanding_type[];
}

type RankCustomTooltipProps = {
  active?: boolean;
  payload?: readonly any[];
  label?: string | number;
  schedule: race_type[];
  hoverDriver: string | null; // 新增這行
};

// 自定義 Tooltip (顯示該站排名)
const RankSingleTooltip = ({ active, payload, label, schedule, hoverDriver }: RankCustomTooltipProps) => {
  if (active && payload && payload.length && hoverDriver) {
    // 因為我們想要單一顯示，通常 payload[0] 就是滑鼠最近或指到的那筆
    const entry = payload.find(p => p.name === hoverDriver);
    if (!entry) return null;
    
    // 找出賽事名稱
    const currentRace = schedule.find(race => parseInt(String(race.round)) === parseInt(String(label) || '0'));
    const raceName = currentRace ? currentRace.raceName : `Round ${label}`;

    return (
      <div className="custom-tooltip">
        <div className="tooltip-header">
           {/* 顯示車手名稱作為標題 */}
          <p className="tooltip-race-name" style={{color: entry.color}}>{entry.name}</p>
          <div style={{display:'flex', justifyContent:'space-between', fontSize:'0.8rem', color:'#ccc'}}>
             <span>{raceName}</span>
          </div>
        </div>
        
        <div className="tooltip-list">
            <div className="tooltip-rank-item">
                <span className="tooltip-rank-position" style={{color: '#fff', fontSize: '1.2rem'}}>P{entry.value}</span>
                <span style={{marginLeft: '10px', color: '#888'}}>Rank</span>
            </div>
        </div>
      </div>
    );
  }
  return null;
};

function RankEvolution({type, year, schedule, standing}: Props) {

  const [rankData, setRankData] = useState<rankEvolution_type[]>([]);
  const [dataKeys, setDataKeys] = useState<string[]>([]);

  const [hoverData, setHoverData] = useState<string | null>(null);

  useEffect(() => {

    setRankData([])
      
    const fetchData = async () => {
      let data: pointsEvolution_type[] = [];
      
      if (type === 'driver') {
        data = await getDriverPointsEvolution(year);
      } else {
        data = await getConstructorPointsEvolution(year);
      }
      
      const rankData = getRankEvolution(data)
      setRankData(rankData);
      console.log(`${type} Evolution Data:`, data);

      if (data.length > 0){
        const keys = Object.keys(data[data.length-1])
        // 過濾掉非參賽者資料的 key
        const validKeys = keys.filter((key) => key !== 'round' && key !== 'name');
        setDataKeys(validKeys)
      }
    };

    fetchData();
  }, [year, type])

  const handleLineHover = (driverKey: string) => {
    setHoverData(driverKey);
  }
  const handleLineLeave = () => {
    setHoverData(null);
  }


  return (
    <div className="standing-chart-container">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rankData} margin={{ top: 5, right: (type === 'constructor' ? 140 : 50), bottom: 20, left: 40 }} onMouseLeave={handleLineLeave}>
          <CartesianGrid strokeDasharray="3 3" stroke="#444" opacity={0.9} horizontal={false} />
          
          <XAxis 
              dataKey="round"
              label={{ value: 'Round', fontWeight: 'bold', position: 'insideBottom', offset: -10, fill: '#fff' }}
              stroke="white"
          />
          <YAxis 
            label={{ value: 'Rank', fontWeight: 'bold', angle: -90, position: 'insideLeft', offset: -20, fill: '#fff' }}
            reversed={true} 
            domain={[1, 'max']} 
            tickCount={10}      
            width={40}
            padding={{ top: 20, bottom: 20 }}
              stroke="white"
          />
          
          <Tooltip 
            content={(props) => <RankSingleTooltip {...props} schedule={schedule} hoverDriver={hoverData} />}
            trigger="hover"
            cursor={false}
          />
          
          {/* 減少 Legend 擁擠，只顯示前幾名或讓使用者互動 highlight */}
          {/* <Legend /> */} 

          {dataKeys.map((key) => {

             let teamColor: string = "#888";
             let displayName: string = key;
                           
            if (type === 'driver') {
              const driver = (standing as driverStanding_type[]).find((driverData) => {
                let driverKey = '';
                if (driverData.Driver.code)
                    driverKey = driverData.Driver.code; 
                else
                    driverKey = driverData.Driver.familyName.slice(0,3).toUpperCase();
                return driverKey === key
              })
              if (!driver) return null;

              teamColor = team_theme[driver.Constructors?.[driver.Constructors.length-1].constructorId];
              displayName = `${driver.Driver.givenName} ${driver.Driver.familyName}`;

            }
            else if (type === 'constructor'){
              const constructor = (standing as constructorStanding_type[]).find((constructorData) => {
                return constructorData.Constructor.constructorId == key;
              })
              if (!constructor) return null;
              teamColor = team_theme[constructor.Constructor.constructorId] || "#888";
              displayName = constructor.Constructor.name;
            }
             const lineOpacity = (hoverData && hoverData !== key) ? 0.6 : 1;
             const strokeWidth = ((hoverData === key) ? 6 : 3) + (type === 'constructor' ? 2 : 0);

             return (<>
              <Line
                key={key} 
                name={displayName}
                type="bump" 
                dataKey={key} 
                stroke={teamColor}
                strokeOpacity={lineOpacity}
                strokeWidth={strokeWidth}

                dot={{ r: 4, fill: 'transparent', strokeWidth: 0 }}
                activeDot={{ 
                  r: 6, 
                  stroke: '#fff', 
                  strokeWidth: 2,
                  onMouseOver: () => handleLineHover(key), // 確保點也能觸發
                  onMouseLeave: handleLineLeave            // 離開點時取消
                }}

                connectNulls={true} // 避免退賽導致斷線

                onMouseEnter={() => handleLineHover(key)}
                onMouseLeave={handleLineLeave}
              >
                <LabelList 
                  key={key}
                  dataKey={key} 
                  position="right" // 文字顯示在點的右邊
                  content={(props: any) => {
                    const { x, y, index, value } = props;
                    // 只在最後一個點顯示
                    if (index === rankData.length - 1 && value !== null) {
                      return (
                        <text 
                          x={x} 
                          y={y} 
                          dy={4} 
                          dx={8} 
                          fill={teamColor} 
                          fontSize={type === 'constructor' ? 16 : 12} 
                          fontWeight="bold"
                          textAnchor="start"
                          opacity={lineOpacity}
                        >
                          {displayName}
                        </text>
                      );
                    }
                    return null;
                  }}
                />
              </Line>
             </>)
          })}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default RankEvolution;