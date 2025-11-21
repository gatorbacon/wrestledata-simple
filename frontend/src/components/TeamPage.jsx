import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import styled from 'styled-components';
import { GetCommand, QueryCommand } from '@aws-sdk/lib-dynamodb';
import { initializeDynamoClient } from '../utils/dynamodb';

const PageContainer = styled.div`
  padding: 20px;
  color: #fff;
`;

const TeamHeader = styled.div`
  margin-bottom: 30px;
`;

const TeamName = styled.h1`
  font-size: 2.5em;
  margin: 0 0 10px 0;
`;

const TeamInfo = styled.div`
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
`;

const InfoItem = styled.div`
  background: rgba(255, 255, 255, 0.1);
  padding: 10px 20px;
  border-radius: 6px;
`;

const InfoLabel = styled.span`
  color: rgba(255, 255, 255, 0.6);
  margin-right: 8px;
`;

const RosterContainer = styled.div`
  margin-top: 30px;
`;

const RosterGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  margin-top: 20px;
`;

const WrestlerCard = styled.div`
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 20px;
`;

const TeamPage = () => {
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const [roster, setRoster] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchTeamData = async () => {
      try {
        const client = initializeDynamoClient();

        // Fetch team data
        const teamResponse = await client.send(new GetCommand({
          TableName: 'teams',
          Key: { team_id: id }
        }));

        if (!teamResponse.Item) {
          throw new Error('Team not found');
        }

        setTeam(teamResponse.Item);

        // Fetch current season roster
        const currentYear = new Date().getFullYear();
        const rosterResponse = await client.send(new QueryCommand({
          TableName: 'season_wrestler',
          IndexName: 'season_team-index',
          KeyConditionExpression: 'team_id = :tid AND season = :year',
          ExpressionAttributeValues: {
            ':tid': id,
            ':year': currentYear
          }
        }));

        setRoster(rosterResponse.Items || []);
        setLoading(false);
      } catch (err) {
        console.error('Error fetching team data:', err);
        setError(err.message);
        setLoading(false);
      }
    };

    fetchTeamData();
  }, [id]);

  if (loading) {
    return (
      <PageContainer>
        <h2>Loading team data...</h2>
      </PageContainer>
    );
  }

  if (error) {
    return (
      <PageContainer>
        <h2>Error loading team data: {error}</h2>
      </PageContainer>
    );
  }

  if (!team) {
    return (
      <PageContainer>
        <h2>Team not found</h2>
      </PageContainer>
    );
  }

  // Sort roster by weight class
  const sortedRoster = [...roster].sort((a, b) => {
    const weightA = parseInt(a.weight_class) || 1000;
    const weightB = parseInt(b.weight_class) || 1000;
    return weightA - weightB;
  });

  return (
    <PageContainer>
      <TeamHeader>
        <TeamName>{team.name}</TeamName>
        <TeamInfo>
          <InfoItem>
            <InfoLabel>Division:</InfoLabel>
            {team.division}
          </InfoItem>
          <InfoItem>
            <InfoLabel>State:</InfoLabel>
            {team.state}
          </InfoItem>
          {team.abbreviation && (
            <InfoItem>
              <InfoLabel>Abbreviation:</InfoLabel>
              {team.abbreviation}
            </InfoItem>
          )}
        </TeamInfo>
      </TeamHeader>

      <RosterContainer>
        <h2>Current Roster</h2>
        <RosterGrid>
          {sortedRoster.map((wrestler) => (
            <WrestlerCard key={wrestler.season_wrestler_id}>
              <h3>{wrestler.name}</h3>
              <TeamInfo>
                <InfoItem>
                  <InfoLabel>Weight:</InfoLabel>
                  {wrestler.weight_class}
                </InfoItem>
                <InfoItem>
                  <InfoLabel>Year:</InfoLabel>
                  {wrestler.class_year}
                </InfoItem>
              </TeamInfo>
            </WrestlerCard>
          ))}
        </RosterGrid>
      </RosterContainer>
    </PageContainer>
  );
};

export default TeamPage; 