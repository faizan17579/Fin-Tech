import React, { useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Chip,
  LinearProgress,
  Alert,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Wifi,
  WifiOff,
  Refresh,
  Assessment,
} from '@mui/icons-material';
import InstrumentDetail from './InstrumentDetail';
import { useAppSelector } from '../hooks/useAppSelector';
import { useAppDispatch } from '../hooks/useAppDispatch';
import { webSocketService } from '../services/websocket';
import { addSubscribedSymbol, removeSubscribedSymbol } from '../store/slices/liveDataSlice';

const Dashboard: React.FC = () => {
  const dispatch = useAppDispatch();
  const { selectedInstrument } = useAppSelector((state) => state.instruments);
  const { livePrices, connected, subscribedSymbols } = useAppSelector((state) => state.liveData);
  const { forecasts } = useAppSelector((state) => state.forecast);

  useEffect(() => {
    webSocketService.connect();
    return () => {
      webSocketService.disconnect();
    };
  }, []);

  useEffect(() => {
    if (selectedInstrument && connected) {
      if (!subscribedSymbols.includes(selectedInstrument)) {
        webSocketService.subscribeToPrice(selectedInstrument);
        dispatch(addSubscribedSymbol(selectedInstrument));
      }
    }
  }, [selectedInstrument, connected, subscribedSymbols, dispatch]);

  const handleRefresh = () => {
    if (selectedInstrument) {
      webSocketService.unsubscribeFromPrice(selectedInstrument);
      webSocketService.subscribeToPrice(selectedInstrument);
    }
  };

  const getCurrentPrice = () => {
    if (!selectedInstrument) return null;
    return livePrices[selectedInstrument];
  };

  const getLatestForecast = () => {
    if (!selectedInstrument) return null;
    return forecasts.find(f => f.symbol === selectedInstrument);
  };

  const currentPrice = getCurrentPrice();
  const latestForecast = getLatestForecast();

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Connection Status */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {connected ? (
                    <Wifi color="success" />
                  ) : (
                    <WifiOff color="error" />
                  )}
                  <Typography variant="h6">
                    Live Data {connected ? 'Connected' : 'Disconnected'}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Chip
                    label={`${subscribedSymbols.length} subscribed`}
                    color={subscribedSymbols.length > 0 ? 'success' : 'default'}
                    variant="outlined"
                  />
                  <Tooltip title="Refresh connection">
                    <IconButton onClick={handleRefresh} size="small">
                      <Refresh />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Current Price Widget */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Current Price
              </Typography>
              {selectedInstrument ? (
                currentPrice ? (
                  <Box>
                    <Typography variant="h4" color="primary">
                      ${currentPrice.price.toFixed(2)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {selectedInstrument} • {new Date(currentPrice.timestamp).toLocaleTimeString()}
                    </Typography>
                  </Box>
                ) : (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <LinearProgress sx={{ flexGrow: 1 }} />
                    <Typography variant="body2" color="text.secondary">
                      Loading price...
                    </Typography>
                  </Box>
                )
              ) : (
                <Alert severity="info">
                  Select an instrument to view live price
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Latest Forecast Widget */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Latest Forecast
              </Typography>
              {selectedInstrument ? (
                latestForecast ? (
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                      <Chip
                        label={latestForecast.model_used}
                        color="primary"
                        size="small"
                      />
                      <Chip
                        label={`${latestForecast.horizon}h horizon`}
                        color="secondary"
                        size="small"
                      />
                    </Box>
                    <Typography variant="h5" color="success.main">
                      ${latestForecast.predicted_values[latestForecast.predicted_values.length - 1]?.toFixed(2) || 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Predicted price in {latestForecast.horizon} hours
                    </Typography>
                    {latestForecast.metrics && (
                      <Box sx={{ mt: 1 }}>
                        <Chip
                          label={`MAPE: ${latestForecast.metrics.mape?.toFixed(2)}%`}
                          color={latestForecast.metrics.mape && latestForecast.metrics.mape < 10 ? 'success' : 'warning'}
                          size="small"
                        />
                      </Box>
                    )}
                  </Box>
                ) : (
                  <Alert severity="info">
                    No forecasts available for {selectedInstrument}
                  </Alert>
                )
              ) : (
                <Alert severity="info">
                  Select an instrument to view forecasts
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Performance Metrics Widget */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <Assessment sx={{ mr: 1, verticalAlign: 'middle' }} />
                Performance Overview
              </Typography>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2">Total Forecasts</Typography>
                  <Chip label={forecasts.length} color="primary" size="small" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2">Active Subscriptions</Typography>
                  <Chip label={subscribedSymbols.length} color="success" size="small" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2">Connection Status</Typography>
                  <Chip
                    label={connected ? 'Online' : 'Offline'}
                    color={connected ? 'success' : 'error'}
                    size="small"
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Instrument detail & training */}
        <Grid item xs={12} md={6}>
          <InstrumentDetail />
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;
