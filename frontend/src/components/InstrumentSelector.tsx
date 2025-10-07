import React, { useEffect, useState } from 'react';
import {
  Box,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Card,
  CardContent,
  Typography,
  Chip,
  Grid,
  InputAdornment,
  Autocomplete,
  Avatar,
  Paper,
  Button,
} from '@mui/material';
import { Search, TrendingUp, TrendingDown } from '@mui/icons-material';
import { useAppSelector } from '../hooks/useAppSelector';
import { useAppDispatch } from '../hooks/useAppDispatch';
import { setSearchTerm, setFilterType, setSelectedInstrument } from '../store/slices/instrumentsSlice';
import { apiService } from '../services/api';

interface InstrumentSelectorProps { compact?: boolean }

const InstrumentSelector: React.FC<InstrumentSelectorProps> = ({ compact = false }) => {
  const dispatch = useAppDispatch();
  const { instruments, selectedInstrument, searchTerm, filterType, loading } = useAppSelector(
    (state) => state.instruments
  );

  const [allInstruments, setAllInstruments] = useState<any[]>([]);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Debounced search function
  useEffect(() => {
    if (!searchTerm.trim()) {
      setSuggestions([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      try {
        setLoadingSuggestions(true);
        const results = await apiService.searchInstruments(searchTerm);
        console.debug('Search results for', searchTerm, results); // debug
        setSuggestions(results);
      } catch (error) {
        console.error('Failed to search instruments:', error);
        setSuggestions([]);
      } finally {
        setLoadingSuggestions(false);
      }
    }, 300); // 300ms debounce

    return () => clearTimeout(timeoutId);
  }, [searchTerm]);

  useEffect(() => {
    const fetchInstruments = async () => {
      try {
        const data = await apiService.getInstruments();
        const instrumentList: any[] = [];
        console.log('Fetched instruments:', data);
        
        // Handle new backend data structure with full objects
        data.stocks?.forEach((item: any) => {
          if (typeof item === 'string') {
            // Old format
            instrumentList.push({ symbol: item, type: 'stock' });
          } else {
            // New format with full object
            instrumentList.push({ 
              symbol: item.symbol, 
              name: item.name,
              sector: item.sector,
              type: 'stock' 
            });
          }
        });
        data.crypto?.forEach((item: any) => {
          if (typeof item === 'string') {
            instrumentList.push({ symbol: item, type: 'crypto' });
          } else {
            instrumentList.push({ 
              symbol: item.symbol, 
              name: item.name,
              sector: item.sector,
              type: 'crypto' 
            });
          }
        });
        data.forex?.forEach((item: any) => {
          if (typeof item === 'string') {
            instrumentList.push({ symbol: item, type: 'forex' });
          } else {
            instrumentList.push({ 
              symbol: item.symbol, 
              name: item.name,
              sector: item.sector,
              type: 'forex' 
            });
          }
        });
        
        console.log('Processed instrument list:', instrumentList);
        setAllInstruments(instrumentList);
        dispatch({ type: 'instruments/setInstruments', payload: instrumentList });
      } catch (error) {
        console.error('Failed to fetch instruments:', error);
        // No fallback data - will show empty list if backend is unavailable
        setAllInstruments([]);
        dispatch({ type: 'instruments/setInstruments', payload: [] });
      }
    };

    fetchInstruments();
  }, [dispatch]);

  const filteredInstruments = allInstruments.filter((instrument) => {
    const matchesSearch = instrument.symbol.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterType === 'all' || instrument.type === filterType;
    return matchesSearch && matchesFilter;
  });

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    dispatch(setSearchTerm(event.target.value));
  };

  const handleFilterChange = (event: any) => {
    dispatch(setFilterType(event.target.value));
  };

  const handleInstrumentSelect = (symbol: string) => {
    dispatch(setSelectedInstrument(symbol));
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'stock':
        return 'primary';
      case 'crypto':
        return 'secondary';
      case 'forex':
        return 'success';
      default:
        return 'default';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'stock':
        return <TrendingUp />;
      case 'crypto':
        return <TrendingDown />;
      case 'forex':
        return <TrendingUp />;
      default:
        return <TrendingUp />;
    }
  };

  return (
    <Box>
      <Box sx={{ mb: compact ? 0 : 2, display: 'flex', gap: 2, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Autocomplete
          fullWidth
          options={suggestions.length ? suggestions : allInstruments.filter(inst => inst.symbol.toLowerCase().includes(searchTerm.toLowerCase())).slice(0, 30)}
          loading={loadingSuggestions}
          getOptionLabel={(option) => option.symbol || ''}
          inputValue={searchTerm}
          onInputChange={(event, newInputValue) => {
            dispatch(setSearchTerm(newInputValue));
          }}
          onChange={(event, newValue) => {
            if (newValue) {
              dispatch(setSelectedInstrument(newValue.symbol));
              dispatch(setSearchTerm(''));
            }
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Search instruments (e.g., AAPL, Bitcoin, Apple)..."
              InputProps={{
                ...params.InputProps,
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
              size={compact ? 'small' : 'medium'}
            />
          )}
          noOptionsText={
            searchTerm.trim() ? (loadingSuggestions ? 'Searching...' : 'No instruments found') : 'Start typing to search...'
          }
          sx={{ flex: '1 1 320px', minWidth: '300px' }}
        />
        <FormControl sx={{ minWidth: 120 }} size={compact ? 'small' : 'medium'}>
          <InputLabel>Type</InputLabel>
          <Select value={filterType} label="Type" onChange={handleFilterChange}>
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="stock">Stocks</MenuItem>
            <MenuItem value="crypto">Crypto</MenuItem>
            <MenuItem value="forex">Forex</MenuItem>
          </Select>
        </FormControl>
        {selectedInstrument && (
          <Button variant='contained' color='primary' onClick={() => console.log('Proceed with', selectedInstrument)} sx={{ whiteSpace: 'nowrap', height: compact ? 40 : 56 }}>
            Proceed
          </Button>
        )}
      </Box>

      {!compact && (
        <Grid container spacing={2}>
          {filteredInstruments.map((instrument) => (
            <Grid item xs={12} sm={6} md={4} key={instrument.symbol}>
              <Card
                sx={{
                  cursor: 'pointer',
                  border: selectedInstrument === instrument.symbol ? 2 : 1,
                  borderColor: selectedInstrument === instrument.symbol ? 'primary.main' : 'divider',
                  '&:hover': { boxShadow: 2 },
                }}
                onClick={() => handleInstrumentSelect(instrument.symbol)}
              >
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Typography variant="h6" component="div">
                      {instrument.symbol}
                    </Typography>
                    <Chip
                      icon={getTypeIcon(instrument.type)}
                      label={instrument.type.toUpperCase()}
                      color={getTypeColor(instrument.type) as any}
                      size="small"
                    />
                  </Box>
                  {instrument.price && (
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                      ${instrument.price.toFixed(2)}
                      {instrument.changePercent && (
                        <Chip
                          label={`${instrument.changePercent > 0 ? '+' : ''}${instrument.changePercent.toFixed(2)}%`}
                          color={instrument.changePercent > 0 ? 'success' : 'error'}
                          size="small"
                          sx={{ ml: 1 }}
                        />
                      )}
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {filteredInstruments.length === 0 && !loading && !compact && (
        <Box sx={{ textAlign: 'center', py: 4 }}>
          <Typography variant="body1" color="text.secondary">
            No instruments found matching your criteria.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default InstrumentSelector;
