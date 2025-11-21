import React from 'react';
import styled from 'styled-components';

const Container = styled.div`
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

const RecruitTools = () => {
  return (
    <Container>
      <Title>Recruit Tools</Title>
      <Subtitle>
        Advanced analytics for coaches and programs to evaluate wrestling talent.
      </Subtitle>
      
      <ComingSoonMessage>
        <ComingSoonText>Recruiting Tools Coming Soon</ComingSoonText>
        <ComingSoonDescription>
          Our recruiting analytics tools are under development. Soon you'll be able to
          analyze recruit performance metrics, compare prospects, and track recruiting classes.
        </ComingSoonDescription>
      </ComingSoonMessage>
    </Container>
  );
};

export default RecruitTools; 