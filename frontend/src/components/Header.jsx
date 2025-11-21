import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import styled from 'styled-components';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faSearch } from '@fortawesome/free-solid-svg-icons';

const HeaderContainer = styled.header`
  background-color: #1a1a1a;
  border-bottom: 1px solid #ffcc00;
  padding: 15px 0;
`;

const HeaderContent = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 20px;
`;

const Logo = styled(Link)`
  display: flex;
  align-items: center;
  font-size: 20px;
  font-weight: 600;
  color: #ffffff;
  text-decoration: none;
`;

const LogoBracket = styled.span`
  color: #62dd92;
`;

const LogoData = styled.span`
  font-weight: 800;
`;

const Nav = styled.nav`
  display: flex;
  gap: 20px;
`;

const NavItem = styled(NavLink)`
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
  transition: color 0.2s;

  &:hover, &.active {
    color: #62dd92;
  }
`;

const SearchContainer = styled.div`
  position: relative;
  display: flex;
  align-items: center;
`;

const SearchInput = styled.input`
  background-color: #666666;
  border: none;
  border-radius: 4px;
  padding: 8px 8px 8px 36px;
  color: #ffffff;
  width: 220px;
  font-size: 14px;

  &::placeholder {
    color: #ffffff;
    opacity: 0.7;
  }
`;

const SearchIcon = styled.div`
  position: absolute;
  left: 10px;
  color: #ffffff;
`;

const Header = () => {
  return (
    <HeaderContainer>
      <HeaderContent>
        <Logo to="/">
          <LogoBracket>[</LogoBracket>
          wrestle
          <LogoData>data</LogoData>
          <LogoBracket>]</LogoBracket>
        </Logo>
        
        <Nav>
          <NavItem to="/wrestlers">Wrestler Profiles</NavItem>
          <NavItem to="/rankings">Rankings</NavItem>
          <NavItem to="/recruit-tools">Recruit Tools</NavItem>
          <NavItem to="/fantasy-brackets">Fantasy Brackets</NavItem>
        </Nav>
        
        <SearchContainer>
          <SearchIcon>
            <FontAwesomeIcon icon={faSearch} size="sm" />
          </SearchIcon>
          <SearchInput
            type="text"
            placeholder="Search wrestlers, teams, events..."
          />
        </SearchContainer>
      </HeaderContent>
    </HeaderContainer>
  );
};

export default Header; 