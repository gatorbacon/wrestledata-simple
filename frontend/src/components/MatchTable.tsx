import React from 'react';
import styled from 'styled-components';

interface Match {
  opponent: {
    name: string;
    team: string;
    record: string;
  };
  result: {
    type: string;
    score: string | null;
    time: string | null;
  };
  weight: string;
  date: string;
  event: string;
}

interface MatchTableProps {
  matches: Match[];
  seasons?: string[];
}

const TableContainer = styled.div`
  overflow-x: auto;
  width: 100%;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  color: white;
  font-weight: 400;
`;

const TableHeader = styled.th`
  text-align: left;
  padding: 8px 16px;
  color: #a0a0a0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.875rem;
`;

const TableRow = styled.tr`
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
`;

const TableCell = styled.td`
  padding: 8px 16px;
`;

const OpponentCell = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const OpponentInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const OpponentName = styled.span`
  font-weight: 500;
`;

const TeamAbbrev = styled.span`
  color: #60a5fa;
  font-size: 0.875rem;
  font-weight: 600;
`;

const Record = styled.span`
  color: #a0a0a0;
  font-size: 0.875rem;
  font-weight: 400;
`;

const EventText = styled.span`
  color: #a0a0a0;
  font-weight: 400;
`;

const ResultBadge = styled.span<{ resultType: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.875rem;
  min-width: 32px;
  background-color: ${props => props.resultType.startsWith('L-') ? '#FF3366' : '#00A99D'};
  border: 2px solid ${props => props.resultType.startsWith('L-') ? '#CC2952' : '#008F85'};
  color: white;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
`;

const ResultContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const ScoreText = styled.span<{ isLoss: boolean }>`
  color: ${props => props.isLoss ? '#FF3366' : '#00A99D'};
  font-weight: 600;
  font-size: 1.125rem;
`;

const getTeamAbbrev = (team: string): string => {
  return team.substring(0, 4).toUpperCase();
};

const getResultColor = (type: string) => {
  const isLoss = type.startsWith('L-');
  const baseType = isLoss ? type.substring(2) : type;
  
  switch (baseType) {
    case 'D': return isLoss ? 'text-red-500' : 'text-white';
    case 'MD': return isLoss ? 'text-red-500' : 'text-white';
    case 'TF': return isLoss ? 'text-red-500' : 'text-white';
    case 'F': return isLoss ? 'text-red-500' : 'text-white';
    default: return 'text-white';
  }
};

const getTeamColor = (team: string) => {
  // Add team color mapping logic here
  return 'text-blue-400';
};

const getResultTypeAndDetails = (result: Match['result']) => {
  const isLoss = result.type.startsWith('L-');
  const baseType = isLoss ? result.type.substring(2) : result.type;
  
  // Return score if it exists, otherwise return time
  const details = result.score || result.time;
  
  return {
    type: baseType,
    originalType: result.type,
    details,
    isLoss
  };
};

const MatchTable: React.FC<{ matches: Match[] }> = ({ matches }) => {
  return (
    <TableContainer>
      <Table>
        <thead>
          <tr>
            <TableHeader>Opponent</TableHeader>
            <TableHeader>Result</TableHeader>
            <TableHeader>Weight</TableHeader>
            <TableHeader>Date</TableHeader>
            <TableHeader>Event</TableHeader>
          </tr>
        </thead>
        <tbody>
          {matches.map((match, index) => {
            const { type, originalType, details, isLoss } = getResultTypeAndDetails(match.result);
            return (
              <TableRow key={index}>
                <TableCell>
                  <OpponentCell>
                    <OpponentInfo>
                      <OpponentName>{match.opponent.name}</OpponentName>
                      <TeamAbbrev>{getTeamAbbrev(match.opponent.team)}</TeamAbbrev>
                    </OpponentInfo>
                    <Record>{match.opponent.record}</Record>
                  </OpponentCell>
                </TableCell>
                <TableCell>
                  <ResultContainer>
                    <ResultBadge resultType={originalType}>{type}</ResultBadge>
                    {details && <ScoreText isLoss={isLoss}>{details}</ScoreText>}
                  </ResultContainer>
                </TableCell>
                <TableCell>{match.weight}</TableCell>
                <TableCell>{match.date}</TableCell>
                <TableCell>
                  <EventText>{match.event}</EventText>
                </TableCell>
              </TableRow>
            );
          })}
        </tbody>
      </Table>
    </TableContainer>
  );
};

export default MatchTable; 