import React from 'react';
import styled from 'styled-components';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faUsers, faTrophy, faDiagramProject, faChartLine } from '@fortawesome/free-solid-svg-icons';
import SearchBar from './SearchBar';

const HomeContainer = styled.div`
  padding: 40px 20px;
  max-width: 1200px;
  margin: 0 auto;
  color: white;
`;

const Hero = styled.div`
  text-align: center;
  margin-bottom: 60px;
`;

const Title = styled.h1`
  font-size: 2.5em;
  margin-bottom: 20px;
`;

const Subtitle = styled.p`
  font-size: 1.2em;
  color: rgba(255, 255, 255, 0.8);
  margin-bottom: 30px;
`;

const SearchSection = styled.div`
  margin-bottom: 60px;
`;

const FeaturesGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 30px;
  margin-top: 60px;
`;

const FeatureCard = styled.div`
  background: rgba(255, 255, 255, 0.1);
  padding: 30px;
  border-radius: 10px;
  text-align: center;
  transition: transform 0.2s;

  &:hover {
    transform: translateY(-5px);
  }
`;

const FeatureIcon = styled(FontAwesomeIcon)`
  font-size: 2em;
  margin-bottom: 20px;
  color: #4CAF50;
`;

const FeatureTitle = styled.h3`
  margin-bottom: 15px;
  font-size: 1.5em;
`;

const FeatureDescription = styled.p`
  color: rgba(255, 255, 255, 0.8);
  font-size: 1em;
  line-height: 1.5;
`;

const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-top: 60px;
  text-align: center;
`;

const StatBox = styled.div`
  padding: 20px;
`;

const StatNumber = styled.div`
  font-size: 2.5em;
  font-weight: bold;
  color: #4CAF50;
  margin-bottom: 10px;
`;

const StatLabel = styled.div`
  color: rgba(255, 255, 255, 0.8);
`;

const HomePage = () => {
  return (
    <HomeContainer>
      <Hero>
        <Title>College Wrestling Data & Analytics</Title>
        <Subtitle>
          Track statistics, analyze performances, and discover insights for
          collegiate wrestling.
        </Subtitle>
        <SearchSection>
          <SearchBar />
        </SearchSection>
      </Hero>

      <FeaturesGrid>
        <FeatureCard>
          <FeatureIcon icon={faUsers} />
          <FeatureTitle>Wrestler Profiles</FeatureTitle>
          <FeatureDescription>
            Comprehensive stats and career history for thousands of collegiate
            wrestlers.
          </FeatureDescription>
        </FeatureCard>

        <FeatureCard>
          <FeatureIcon icon={faTrophy} />
          <FeatureTitle>Rankings</FeatureTitle>
          <FeatureDescription>
            Current and historical rankings across all divisions and weight
            classes.
          </FeatureDescription>
        </FeatureCard>

        <FeatureCard>
          <FeatureIcon icon={faChartLine} />
          <FeatureTitle>Recruit Tools</FeatureTitle>
          <FeatureDescription>
            Advanced analytics for coaches and programs to evaluate talent.
          </FeatureDescription>
        </FeatureCard>

        <FeatureCard>
          <FeatureIcon icon={faDiagramProject} />
          <FeatureTitle>Fantasy Brackets</FeatureTitle>
          <FeatureDescription>
            Create your own tournament brackets and predict match outcomes.
          </FeatureDescription>
        </FeatureCard>
      </FeaturesGrid>

      <StatsGrid>
        <StatBox>
          <StatNumber>18,750</StatNumber>
          <StatLabel>Wrestlers</StatLabel>
        </StatBox>
        <StatBox>
          <StatNumber>124,350</StatNumber>
          <StatLabel>Matches</StatLabel>
        </StatBox>
        <StatBox>
          <StatNumber>547</StatNumber>
          <StatLabel>Teams</StatLabel>
        </StatBox>
        <StatBox>
          <StatNumber>892</StatNumber>
          <StatLabel>Tournaments</StatLabel>
        </StatBox>
      </StatsGrid>
    </HomeContainer>
  );
};

export default HomePage; 