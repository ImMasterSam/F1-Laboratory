import type { pointsEvolution_type, rankEvolution_type, driverStanding_type, constructorStanding_type } from "../Type/StandingTypes";
import { fetchScheduleList, getConstructorStandingByRound, getDriverStandingByRound } from "./Fetch";

export async function getDriverPointsEvolution(year: number): Promise<pointsEvolution_type[]> {
    try {

        // Fetch schedule to know how many rounds there are in the season
        const schedule = await fetchScheduleList(year);
        const totalRounds = schedule.length;

        // Points evolution data structure
        const evolutionData: pointsEvolution_type[] = [];
        const results = [];

        // To avoid sending too many requests at once, we can fetch standings round by round with a small delay
        for (let round = 1; round <= totalRounds; round++) {
            await new Promise(r => setTimeout(r, 10));

            try {
                let standings = await getDriverStandingByRound(year, round);
                results.push({ round, standings });
            } catch (err) {
                console.warn(`Failed to fetch rnd ${round}`, err);
            }
        }

        // Data Processing
        results.sort((a, b) => a.round - b.round);

        results.forEach(({ round, standings }) => {
            const roundData: pointsEvolution_type = {
                round: `${round}`, // X Axis label
            };

            standings.forEach((driver: driverStanding_type) => {
                // Using driver code as key and points as value for the line chart
                let driverKey = '';
                if (driver.Driver.code)
                    driverKey = driver.Driver.code;
                else {
                    driverKey = driver.Driver.familyName.slice(0, 3).toUpperCase();
                }
                roundData[driverKey] = parseFloat(driver.points as unknown as string);
            });

            evolutionData.push(roundData);
        });

        return evolutionData;

    } catch (error) {
        console.error("Error fetching points evolution:", error);
        return [];
    }
}

export async function getConstructorPointsEvolution(year: number): Promise<pointsEvolution_type[]> {
    try {

        // Fetch schedule to know how many rounds there are in the season
        const schedule = await fetchScheduleList(year);
        const totalRounds = schedule.length;

        // Points evolution data structure
        const evolutionData: pointsEvolution_type[] = [];
        const results = [];

        // To avoid sending too many requests at once, we can fetch standings round by round with a small delay
        for (let round = 1; round <= totalRounds; round++) {
            await new Promise(r => setTimeout(r, 10));

            try {
                let standings = await getConstructorStandingByRound(year, round);
                results.push({ round, standings });
            } catch (err) {
                console.warn(`Failed to fetch rnd ${round}`, err);
            }
        }

        console.log("Constructor Standings by Round:", results);

        // Data Processing
        results.sort((a, b) => a.round - b.round);

        results.forEach(({ round, standings }) => {
            const roundData: pointsEvolution_type = {
                round: `${round}`, // X Axis label
            };

            standings.forEach((constructor: constructorStanding_type) => {
                // Using constructor name as key and points as value for the line chart
                roundData[constructor.Constructor.name] = parseFloat(constructor.points as unknown as string);
            });

            evolutionData.push(roundData);
        });

        return evolutionData;

    } catch (error) {
        console.error("Error fetching points evolution:", error);
        return [];
    }
}

export function getRankEvolution(pointsData: pointsEvolution_type[]): rankEvolution_type[] {

    // Data Processing
    const rankData: rankEvolution_type[] = pointsData.map((roundData) => {
        const { name, round, ...driverPoints } = roundData;

        // 將該站所有車手的積分取出來排序
        const sortedDivers = Object.entries(driverPoints)
            .sort(([, pointsA], [, pointsB]) => (pointsB as number) - (pointsA as number))
            .map(([driverCode]) => driverCode);

        // 建立新的物件，將積分替換為排名
        const newRoundData: any = { name, round };

        // 填入排名 (index + 1)
        Object.keys(driverPoints).forEach(driver => {
            const rank = sortedDivers.indexOf(driver) + 1;
            newRoundData[driver] = rank;
        });

        return newRoundData;
    });

    return rankData;
}
