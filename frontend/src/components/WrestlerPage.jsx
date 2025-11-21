import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import styled from 'styled-components';
import { GetCommand, QueryCommand, ScanCommand } from '@aws-sdk/lib-dynamodb';
import { initializeDynamoClient } from '../utils/dynamodb';
import MatchTable from './MatchTable';

const PageContainer = styled.div`
  padding: 20px;
  color: #fff;
  max-width: 1600px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const TopSection = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
`;

const BottomSection = styled.div`
  width: 100%;
`;

const LeftColumn = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const RightColumn = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
`;

const WrestlerHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
`;

const ProfileImage = styled.div`
  width: 100px;
  height: 100px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
`;

const WrestlerNameContainer = styled.div`
  flex: 1;
`;

const WrestlerName = styled.h1`
  font-size: 2em;
  margin: 0;
`;

const WrestlerClass = styled.div`
  color: #0088cc;
  font-size: 1.2em;
`;

const RefreshButton = styled.button`
  background: transparent;
  border: none;
  color: #0088cc;
  cursor: pointer;
  font-size: 1.5em;
`;

const StatsCard = styled.div`
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 20px;
`;

const RadarChart = styled.div`
  width: 100%;
  height: 300px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  margin: 20px 0;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
`;

const StatSection = styled.div`
  h3 {
    margin: 0 0 10px 0;
    color: rgba(255, 255, 255, 0.6);
  }
`;

const StatRow = styled.div`
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
`;

const RankingsCard = styled.div`
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 20px;
`;

const RankingsTable = styled.div`
  width: 100%;
  margin-top: 20px;
`;

const TrendChart = styled.div`
  width: 100%;
  height: 200px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  margin-top: 20px;
`;

const LoadMoreButton = styled.button`
  background: rgba(255, 255, 255, 0.1);
  color: white;
  border: none;
  padding: 8px 16px;
  border-radius: 4px;
  margin-top: 10px;
  cursor: pointer;
  &:hover {
    background: rgba(255, 255, 255, 0.2);
  }
`;

const WrestlerPage = () => {
  const { careerId } = useParams();
  const [wrestler, setWrestler] = useState(null);
  const [seasons, setSeasons] = useState([]);
  const [matches, setMatches] = useState({});
  const [visibleMatches, setVisibleMatches] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const MATCHES_PER_PAGE = 5;

  useEffect(() => {
    const fetchWrestlerData = async () => {
      try {
        const client = initializeDynamoClient();

        // 1. Get career wrestler data
        const careerResponse = await client.send(new GetCommand({
          TableName: 'career_wrestler',
          Key: { career_id: careerId }
        }));

        if (!careerResponse.Item) {
          throw new Error('Wrestler not found');
        }
        setWrestler(careerResponse.Item);

        // 2. Get all season_wrestler_ids for this career_id
        const seasonsResponse = await client.send(new QueryCommand({
          TableName: 'season_wrestler',
          IndexName: 'career_id-index',
          KeyConditionExpression: 'career_id = :cid',
          ExpressionAttributeValues: {
            ':cid': careerId
          }
        }));

        const seasonItems = seasonsResponse.Items || [];
        setSeasons(seasonItems);

        // 3. Batch fetch matches for all season_wrestler_ids using GSIs
        const initialMatches = {};
        const initialVisible = {};

        // Get all season_wrestler_ids
        const seasonWrestlerIds = seasonItems.map(s => s.season_wrestler_id);
        
        if (seasonWrestlerIds.length === 0) {
          setMatches({});
          setVisibleMatches({});
          setLoading(false);
          return;
        }

        // Query matches for each wrestler using the GSIs
        const matchPromises = [];

        // Query for matches where wrestler is winner
        for (const id of seasonWrestlerIds) {
          matchPromises.push(
            client.send(new QueryCommand({
              TableName: 'matches',
              IndexName: 'winner_id-index',
              KeyConditionExpression: 'winner_id = :wid',
              ExpressionAttributeValues: { ':wid': id }
            }))
          );
        }

        // Query for matches where wrestler is loser
        for (const id of seasonWrestlerIds) {
          matchPromises.push(
            client.send(new QueryCommand({
              TableName: 'matches',
              IndexName: 'loser_id-index',
              KeyConditionExpression: 'loser_id = :lid',
              ExpressionAttributeValues: { ':lid': id }
            }))
          );
        }

        // Wait for all match queries to complete
        const matchResponses = await Promise.all(matchPromises);
        
        // Process all match responses
        const allMatches = matchResponses.flatMap(response => response.Items || []);
        console.log(`Found ${allMatches.length} total matches before deduplication`);

        // Process and organize matches by season_wrestler_id
        seasonWrestlerIds.forEach(seasonWrestlerId => {
          // Find matches for this season wrestler
          const seasonMatches = allMatches.filter(match => 
            match.winner_id === seasonWrestlerId || 
            match.loser_id === seasonWrestlerId
          );

          // Remove duplicates based on match_id (in case a match appears in both queries)
          const uniqueMatches = Array.from(
            new Map(seasonMatches.map(match => [match.match_id, match])).values()
          );

          // Sort by date (oldest to newest - chronological order)
          uniqueMatches.sort((a, b) => new Date(a.date) - new Date(b.date));

          initialMatches[seasonWrestlerId] = uniqueMatches;
          initialVisible[seasonWrestlerId] = MATCHES_PER_PAGE;

          // Log match counts for debugging
          console.log(`Found ${uniqueMatches.length} matches for ${seasonWrestlerId}`);
          if (uniqueMatches.length > 0) {
            console.log('Sample match:', {
              matchId: uniqueMatches[0].match_id,
              result: uniqueMatches[0].result,
              date: uniqueMatches[0].date
            });
          }
        });

        setMatches(initialMatches);
        setVisibleMatches(initialVisible);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching wrestler data:', err);
        setError(err.message);
        setLoading(false);
      }
    };

    if (careerId) {
      fetchWrestlerData();
    } else {
      setError('No wrestler ID provided');
      setLoading(false);
    }
  }, [careerId]);

  const loadMoreMatches = (seasonWrestlerId) => {
    setVisibleMatches(prev => ({
      ...prev,
      [seasonWrestlerId]: prev[seasonWrestlerId] + MATCHES_PER_PAGE
    }));
  };
  
  // Calculate season stats
  const calculateSeasonStats = (seasonWrestlerId) => {
    const seasonMatches = matches[seasonWrestlerId] || [];
    console.log(`Calculating stats for ${seasonWrestlerId}`, seasonMatches);
    
    const wins = seasonMatches.filter(match => match.winner_id === seasonWrestlerId).length;
    const total = seasonMatches.length;
    const losses = total - wins;
    
    console.log(`Stats calculated: ${wins}-${losses} (${total} total)`);
    return { wins, losses, total };
  };

  const formatMatchesForTable = (seasonMatches, seasonWrestlerId) => {
    return seasonMatches.slice(0, visibleMatches[seasonWrestlerId]).map(match => {
      console.log('Formatting match:', match); // Debug log
      
      // Parse the result
      const result = match.result || 'D-0-0';
      
      // Determine if current wrestler is winner or loser
      const isWinner = match.winner_id === seasonWrestlerId;
      
      // Get opponent data based on whether current wrestler is winner or loser
      const opponentId = isWinner ? match.loser_id : match.winner_id;
      const opponentName = isWinner ? match.loser_name : match.winner_name;
      const opponentTeam = isWinner ? match.loser_team : match.winner_team;
      const opponentRecord = isWinner ? match.loser_record : match.winner_record;

      // Extract result type and details
      let resultType = 'D'; // Default to Decision
      let score = null;
      let time = null;

      if (result.includes('Fall')) {
        resultType = 'F';
        time = result.replace('Fall', '').trim();
      } else if (result.includes('TF')) {
        resultType = 'TF';
        const parts = result.split(' ');
        if (parts.length > 1) {
          score = parts[1];
          if (parts.length > 2) {
            time = parts[2];
          }
        }
      } else if (result.includes('MD')) {
        resultType = 'MD';
        score = result.replace('MD', '').trim();
      } else if (result.includes('Dec')) {
        resultType = 'D';
        score = result.replace('Dec', '').trim();
      }
      
      // If current wrestler lost, make sure displayed result reflects it
      if (!isWinner) {
        resultType = 'L-' + resultType; // Prefix with 'L-' to indicate loss
      }

      // Extract weight from the match
      const weight = match.weight || 'Unknown';

      return {
        opponent: {
          name: opponentName || "Unknown",
          team: opponentTeam || "",
          record: opponentRecord ? `(${opponentRecord})` : '(23-3)'  // Format record with parentheses
        },
        result: {
          type: resultType,
          score: score,
          time: time
        },
        weight: weight,
        date: match.date || 'Unknown Date',
        event: match.event || ''
      };
    });
  };

  if (loading) {
    return (
      <PageContainer>
        <h2>Loading wrestler data...</h2>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer>
        <h2>Error loading wrestler data: {error}</h2>
      </PageContainer>
    );
  }

  if (!wrestler) {
    return (
      <PageContainer>
        <h2>Wrestler not found</h2>
      </PageContainer>
    );
  }

  // Sort seasons by year descending
  const sortedSeasons = [...seasons].sort((a, b) => b.season - a.season);

  return (
    <PageContainer>
      <TopSection>
        <LeftColumn>
          <WrestlerHeader>
            <ProfileImage />
            <WrestlerNameContainer>
              <WrestlerName>
                {wrestler?.name?.toUpperCase() || 'Loading...'}
              </WrestlerName>
              <WrestlerClass>freshman</WrestlerClass>
            </WrestlerNameContainer>
            <RefreshButton>⟳</RefreshButton>
          </WrestlerHeader>

          <RadarChart>
            Radar Chart Placeholder
          </RadarChart>

          <StatsGrid>
            <StatSection>
              <h3>2025</h3>
              <StatRow>
                <span>RPI</span>
                <span>0.856</span>
              </StatRow>
              <StatRow>
                <span>Record</span>
                <span>27-3</span>
              </StatRow>
              <StatRow>
                <span>Winning %</span>
                <span>90.0%</span>
              </StatRow>
              <StatRow>
                <span>Bonus %</span>
                <span>72.1%</span>
              </StatRow>
            </StatSection>

            <StatSection>
              <h3>CAREER</h3>
              <StatRow>
                <span>RPI</span>
                <span>0.856</span>
              </StatRow>
              <StatRow>
                <span>Record</span>
                <span>27-3</span>
              </StatRow>
              <StatRow>
                <span>Winning %</span>
                <span>90.0%</span>
              </StatRow>
              <StatRow>
                <span>Bonus %</span>
                <span>72.1%</span>
              </StatRow>
            </StatSection>
          </StatsGrid>
        </LeftColumn>

        <RightColumn>
          <RankingsCard>
            <h2>Rankings Comparison</h2>
            <RankingsTable>Rankings Table Placeholder</RankingsTable>
            <TrendChart>Trend Chart Placeholder</TrendChart>
          </RankingsCard>
        </RightColumn>
      </TopSection>

      <BottomSection>
        {seasons.map((season) => (
          <div key={season.season_wrestler_id}>
            {matches[season.season_wrestler_id] && (
              <MatchTable
                matches={formatMatchesForTable(
                  matches[season.season_wrestler_id].slice(0, visibleMatches[season.season_wrestler_id]),
                  season.season_wrestler_id
                )}
                seasonWrestlerId={season.season_wrestler_id}
              />
            )}
            {matches[season.season_wrestler_id]?.length > visibleMatches[season.season_wrestler_id] && (
              <LoadMoreButton onClick={() => loadMoreMatches(season.season_wrestler_id)}>
                Load More Matches
              </LoadMoreButton>
            )}
          </div>
        ))}
      </BottomSection>
    </PageContainer>
  );
};

export default WrestlerPage; 