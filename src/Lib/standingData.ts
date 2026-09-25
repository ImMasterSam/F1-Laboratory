import type { pointsEvolution_type, rankEvolution_type } from "../Type/StandingTypes";

export async function getDriverPointsEvolution(year: number): Promise<pointsEvolution_type[]> {
    try {
        const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';
        const response = await fetch(`${API_URL}/standings/${year}/drivers`);
        if (!response.ok) {
            console.error(`Failed to fetch driver standings for year ${year} from backend.`);
            return [];
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error("Error fetching points evolution from backend:", error);
        return [];
    }
}

export async function getConstructorPointsEvolution(year: number): Promise<pointsEvolution_type[]> {
    try {
        const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5001';
        const response = await fetch(`${API_URL}/standings/${year}/constructors`);
        if (!response.ok) {
            console.error(`Failed to fetch constructor standings for year ${year} from backend.`);
            return [];
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error("Error fetching constructor points evolution from backend:", error);
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
