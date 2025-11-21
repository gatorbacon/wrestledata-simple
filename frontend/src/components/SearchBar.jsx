import React, { useState, useEffect, useMemo } from 'react';
import styled from 'styled-components';
import Fuse from 'fuse.js';
import { Link } from 'react-router-dom';
import { ScanCommand } from '@aws-sdk/lib-dynamodb';
import { initializeDynamoClient } from '../utils/dynamodb';

const SearchContainer = styled.div`
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  position: relative;
`;

const SearchInput = styled.input`
  width: 100%;
  padding: 12px 20px;
  border: none;
  border-radius: 6px;
  background-color: rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 16px;
  
  &::placeholder {
    color: rgba(255, 255, 255, 0.6);
  }
  
  &:focus {
    outline: none;
    background-color: rgba(255, 255, 255, 0.15);
  }
`;

const SearchIcon = styled.span`
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: rgba(255, 255, 255, 0.6);
`;

const ResultsContainer = styled.div`
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #2a2a2a;
  border-radius: 6px;
  margin-top: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  display: ${props => props.$show ? 'flex' : 'none'};
  gap: 20px;
  padding: 16px;
`;

const ResultsSection = styled.div`
  flex: 1;
`;

const ResultsTitle = styled.h3`
  color: #fff;
  font-size: 18px;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
`;

const ResultsList = styled.ul`
  list-style: none;
  padding: 0;
  margin: 0;
`;

const ResultItem = styled.li`
  padding: 8px 12px;
  color: #fff;
  cursor: pointer;
  border-radius: 4px;
  
  &:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }
`;

const loadAllWrestlers = async (client) => {
  let allWrestlers = [];
  let lastEvaluatedKey = undefined;

  try {
    console.log('Starting to load wrestlers...');
    do {
      const params = {
        TableName: 'career_wrestler',
        ExclusiveStartKey: lastEvaluatedKey,
      };

      console.log('Fetching wrestlers with params:', params);
      const response = await client.send(new ScanCommand(params));
      console.log('Received response:', response);
      
      if (response.Items) {
        allWrestlers = [...allWrestlers, ...response.Items];
      }
      lastEvaluatedKey = response.LastEvaluatedKey;
    } while (lastEvaluatedKey);

    console.log('Total wrestlers loaded:', allWrestlers.length);
    return allWrestlers;
  } catch (error) {
    console.error('Error loading wrestlers:', error);
    return [];
  }
};

const loadAllSchools = async (client) => {
  let allSchools = [];
  let lastEvaluatedKey = undefined;

  try {
    console.log('Starting to load schools...');
    do {
      const params = {
        TableName: 'teams',
        ExclusiveStartKey: lastEvaluatedKey,
      };

      console.log('Fetching schools with params:', params);
      const response = await client.send(new ScanCommand(params));
      console.log('Received response:', response);
      
      if (response.Items) {
        allSchools = [...allSchools, ...response.Items];
      }
      lastEvaluatedKey = response.LastEvaluatedKey;
    } while (lastEvaluatedKey);

    console.log('Total schools loaded:', allSchools.length);
    return allSchools;
  } catch (error) {
    console.error('Error loading schools:', error);
    return [];
  }
};

const SearchBar = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedTerm, setDebouncedTerm] = useState('');
  const [results, setResults] = useState({ wrestlers: [], schools: [] });
  const [showResults, setShowResults] = useState(false);
  const [isConfigured, setIsConfigured] = useState(false);
  const [docClient, setDocClient] = useState(null);
  const [allWrestlers, setAllWrestlers] = useState([]);
  const [allSchools, setAllSchools] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Initialize DynamoDB client and fetch all data on component mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const client = initializeDynamoClient();
        setDocClient(client);
        setIsConfigured(!!client);

        console.log('Initializing data fetch...');
        const wrestlers = await loadAllWrestlers(client);
        console.log('Wrestlers loaded:', wrestlers.length);
        const schools = await loadAllSchools(client);
        console.log('Schools loaded:', schools.length);
        
        if (wrestlers.length === 0 && schools.length === 0) {
          console.error('No data loaded from either table');
          setError('Unable to load search data');
        }

        setAllWrestlers(wrestlers);
        setAllSchools(schools);
      } catch (err) {
        console.error('Error during initial data load:', err);
        setError('Failed to load search data');
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, []);

  // Debounce the search term
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setDebouncedTerm(searchTerm);
    }, 300);

    return () => clearTimeout(timeoutId);
  }, [searchTerm]);

  // Create Fuse.js indexes
  const wrestlerFuse = useMemo(() => {
    return new Fuse(allWrestlers, {
      keys: ['name_variants'],
      threshold: 0.3
    });
  }, [allWrestlers]);

  const schoolFuse = useMemo(() => {
    return new Fuse(allSchools, {
      keys: ['name'],
      threshold: 0.4,
      includeScore: true
    });
  }, [allSchools]);

  // Execute search when debounced term changes
  useEffect(() => {
    if (debouncedTerm && isConfigured) {
      searchDatabase(debouncedTerm);
    }
  }, [debouncedTerm, isConfigured]);

  const searchDatabase = (term) => {
    console.log('Searching for term:', term);
    if (!term.trim()) {
      console.log('Empty search term, clearing results');
      setResults({ wrestlers: [], schools: [] });
      setShowResults(false);
      return;
    }

    if (!allWrestlers.length && !allSchools.length) {
      console.log('No data available for search');
      return;
    }

    console.log('Current wrestler index:', wrestlerFuse);
    console.log('Current school index:', schoolFuse);
    console.log('Total wrestlers available:', allWrestlers.length);
    console.log('Total schools available:', allSchools.length);
    
    const matchingWrestlers = wrestlerFuse.search(term).map(r => r.item).slice(0, 20);
    const matchingSchools = schoolFuse.search(term)
      .sort((a, b) => a.score - b.score)
      .map(r => r.item)
      .slice(0, 10);

    console.log('Found wrestlers:', matchingWrestlers);
    console.log('Found schools:', matchingSchools);

    setResults({
      wrestlers: matchingWrestlers.map(w => {
        console.log('Processing wrestler:', w);
        console.log('Raw career_id:', w.career_id);
        const wrestlerResult = {
          name: getWrestlerName(w),
          id: w.career_id
        };
        console.log('Generated wrestler result:', wrestlerResult);
        return wrestlerResult;
      }),
      schools: matchingSchools.map(s => ({
        name: s.name,
        id: s.team_id,
        division: s.division
      }))
    });
    setShowResults(true);
  };

  // Helper function to check if a wrestler matches the search term
  const isWrestlerMatch = (wrestler, term) => {
    // Check if name_variants exists and is an array
    if (!wrestler.name_variants || !Array.isArray(wrestler.name_variants)) {
      return false;
    }
    
    // Check each name variant for a match
    return wrestler.name_variants.some(nameObj => {
      // Handle both string values and DynamoDB attribute value objects
      const nameValue = typeof nameObj === 'string' ? nameObj :
                        nameObj.S ? nameObj.S : null;
      
      if (!nameValue) return false;
      return nameValue.toLowerCase().includes(term);
    });
  };

  // Helper function to extract wrestler name
  const getWrestlerName = (wrestler) => {
    if (!wrestler.name_variants || !Array.isArray(wrestler.name_variants)) {
      return 'Unknown Wrestler';
    }
    
    const nameObj = wrestler.name_variants[0];
    return typeof nameObj === 'string' ? nameObj :
           nameObj.S ? nameObj.S : 'Unknown Wrestler';
  };

  const handleSearch = (e) => {
    const value = e.target.value;
    console.log('Search input changed:', value);
    setSearchTerm(value);
    
    if (!isConfigured) {
      console.error('AWS client not properly configured');
    }
  };

  if (isLoading) {
    return (
      <SearchContainer>
        <SearchInput
          type="text"
          placeholder="Loading search data..."
          disabled
        />
      </SearchContainer>
    );
  }

  if (error) {
    return (
      <SearchContainer>
        <SearchInput
          type="text"
          placeholder={error}
          disabled
        />
      </SearchContainer>
    );
  }

  return (
    <SearchContainer>
      <SearchIcon>🔍</SearchIcon>
      <SearchInput
        type="text"
        placeholder="Search wrestlers, teams, or tournaments..."
        value={searchTerm}
        onChange={handleSearch}
        onFocus={() => debouncedTerm && setShowResults(true)}
      />
      <ResultsContainer $show={showResults && (results.wrestlers.length > 0 || results.schools.length > 0)}>
        {results.wrestlers.length > 0 && (
          <ResultsSection>
            <ResultsTitle>Wrestlers</ResultsTitle>
            <ResultsList>
              {results.wrestlers.map((wrestler, index) => {
                console.log('Rendering wrestler link:', wrestler);
                console.log('Generated URL:', `/wrestler/${wrestler.id}`);
                return (
                  <ResultItem key={index}>
                    <Link to={`/wrestler/${wrestler.id}`} style={{ color: '#fff', textDecoration: 'none' }}>
                      {wrestler.name}
                    </Link>
                  </ResultItem>
                );
              })}
            </ResultsList>
          </ResultsSection>
        )}
        {results.schools.length > 0 && (
          <ResultsSection>
            <ResultsTitle>Schools</ResultsTitle>
            <ResultsList>
              {results.schools.map((school, index) => (
                <ResultItem key={index}>
                  <Link to={`/team/${school.id}`} style={{ color: '#fff', textDecoration: 'none' }}>
                    {school.name}
                  </Link>
                </ResultItem>
              ))}
            </ResultsList>
          </ResultsSection>
        )}
      </ResultsContainer>
    </SearchContainer>
  );
};

export default SearchBar; 