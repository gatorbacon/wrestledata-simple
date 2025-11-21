import React from 'react';
import styled from 'styled-components';
import { Link } from 'react-router-dom';

const FooterContainer = styled.footer`
  background-color: #1a1a1a;
  border-top: 1px solid #333;
  padding: 30px 0;
  margin-top: 40px;
`;

const FooterContent = styled.div`
  display: flex;
  justify-content: space-between;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;

  @media (max-width: 768px) {
    flex-direction: column;
    gap: 20px;
  }
`;

const FooterSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
`;

const FooterLogo = styled(Link)`
  display: flex;
  align-items: center;
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
  text-decoration: none;
  margin-bottom: 10px;
`;

const LogoBracket = styled.span`
  color: #62dd92;
`;

const LogoData = styled.span`
  font-weight: 800;
`;

const FooterLinks = styled.div`
  display: flex;
  gap: 15px;
`;

const FooterLink = styled(Link)`
  color: #999;
  font-size: 14px;
  text-decoration: none;
  transition: color 0.2s;

  &:hover {
    color: #ffffff;
  }
`;

const Copyright = styled.p`
  color: #666;
  font-size: 12px;
  margin-top: 8px;
`;

const Footer = () => {
  const currentYear = new Date().getFullYear();

  return (
    <FooterContainer>
      <FooterContent>
        <FooterSection>
          <FooterLogo to="/">
            <LogoBracket>[</LogoBracket>
            wrestle
            <LogoData>data</LogoData>
            <LogoBracket>]</LogoBracket>
          </FooterLogo>
          <Copyright>© {currentYear} wrestledata.com. All rights reserved.</Copyright>
        </FooterSection>

        <FooterSection>
          <FooterLinks>
            <FooterLink to="/about">About</FooterLink>
            <FooterLink to="/contact">Contact</FooterLink>
            <FooterLink to="/privacy">Privacy</FooterLink>
            <FooterLink to="/terms">Terms</FooterLink>
          </FooterLinks>
        </FooterSection>
      </FooterContent>
    </FooterContainer>
  );
};

export default Footer; 