import React from 'react';
import styled from 'styled-components';

const ProfileContainer = styled.div`
  padding: 20px;
`;

const Title = styled.h1`
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 20px;
  color: #ffffff;
`;

const Subtitle = styled.p`
  font-size: 16px;
  color: #cccccc;
  margin-bottom: 30px;
`;

const ComingSoonMessage = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background-color: #222;
  border-radius: 8px;
  padding: 60px 20px;
  text-align: center;
`;

const ComingSoonText = styled.h2`
  font-size: 24px;
  color: #62dd92;
  margin-bottom: 15px;
`;

const ComingSoonDescription = styled.p`
  font-size: 16px;
  color: #cccccc;
  max-width: 600px;
`;

const WrestlerProfiles = () => {
  return (
    <ProfileContainer>
      <Title>Wrestler Profiles</Title>
      <Subtitle>
        Explore detailed statistics and career information for college wrestlers.
      </Subtitle>
      
      <ComingSoonMessage>
        <ComingSoonText>Profile Content Coming Soon</ComingSoonText>
        <ComingSoonDescription>
          We're currently loading data for thousands of wrestlers. Check back soon for comprehensive profiles, 
          match histories, and performance analytics.
        </ComingSoonDescription>
      </ComingSoonMessage>
    </ProfileContainer>
  );
};

export default WrestlerProfiles; 