import React from 'react';

interface Match {
  opponent: {
    name: string;
    team: string;
    rank?: number;
  };
  result: {
    type: 'D' | 'MD' | 'TF' | 'F';
    score?: string;
    time?: string;
  };
  weight: number;
  date: string;
}

interface MatchTableProps {
  matches: Match[];
}

const getResultColor = (type: string) => {
  switch (type) {
    case 'D': return 'bg-cyan-500';
    case 'MD': return 'bg-pink-500';
    case 'TF': return 'bg-emerald-500';
    case 'F': return 'bg-green-500';
    default: return 'bg-gray-500';
  }
};

const getResultText = (result: Match['result']) => {
  if (result.time) {
    return result.time;
  }
  return result.score;
};

export default function MatchTable({ matches }: MatchTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full bg-black/50 backdrop-blur-sm">
        <thead>
          <tr className="border-b border-white/10">
            <th className="text-left p-3 text-gray-300">Opponent</th>
            <th className="p-3 text-gray-300">Result</th>
            <th className="p-3 text-gray-300">Weight</th>
            <th className="p-3 text-gray-300">Date</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((match, i) => (
            <tr key={i} className="border-b border-white/10">
              <td className="p-3">
                <div className="flex items-center gap-2">
                  {match.opponent.rank && (
                    <span className="text-gray-400">#{match.opponent.rank}</span>
                  )}
                  <span className="font-medium">{match.opponent.name}</span>
                  <span className="text-sm text-gray-400">{match.opponent.team}</span>
                </div>
              </td>
              <td className="p-3">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getResultColor(match.result.type)}`}>
                  {match.result.type} {getResultText(match.result)}
                </span>
              </td>
              <td className="p-3 text-center">{match.weight}</td>
              <td className="p-3 text-gray-300">{match.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
} 