import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TextField,
  Button,
  Grid,
  Alert,
  CircularProgress,
  Chip,
} from '@mui/material';
import { PlayArrow, History } from '@mui/icons-material';
import { useAppSelector } from '../hooks/useAppSelector';
import { useAppDispatch } from '../hooks/useAppDispatch';
import { setSelectedHorizon, setSelectedModel, addForecast, setLoading, setError, clearError } from '../store/slices/forecastSlice';
import { apiService } from '../services/api';

const ForecastControl: React.FC = () => {
  const dispatch = useAppDispatch();
  const { selectedInstrument } = useAppSelector((state) => state.instruments);
  const { selectedHorizon, selectedModel, loading, error } = useAppSelector((state) => state.forecast);
  const [localHorizon, setLocalHorizon] = useState(selectedHorizon);
  const [selectedModels, setSelectedModels] = useState<string[]>(['SMA','EMA','LSTM']);
  const [windowSize, setWindowSize] = useState<number>(48);
  const [epochs, setEpochs] = useState<number>(20);
  const [includeEnsemble, setIncludeEnsemble] = useState<boolean>(true);

  const horizonOptions = [
    { value: 1, label: '1 Hour' },
    { value: 3, label: '3 Hours' },
    { value: 6, label: '6 Hours' },
    { value: 12, label: '12 Hours' },
    { value: 24, label: '1 Day' },
    { value: 72, label: '3 Days' },
    { value: 168, label: '1 Week' },
  ];

  const modelOptions = [
    { value: 'SMA', label: 'SMA (20)' },
    { value: 'EMA', label: 'EMA (20)' },
    { value: 'ARIMA', label: 'ARIMA' },
    { value: 'LSTM', label: 'LSTM' },
  ];

  const modelDescriptions: Record<string,string> = {
    SMA: 'Simple Moving Average baseline (window=20)',
    EMA: 'Exponential Moving Average (faster reaction)',
    ARIMA: 'ARIMA time-series model (captures autocorrelation)',
    LSTM: 'Neural sequence model (captures nonlinear temporal patterns)',
    ENSEMBLE: 'Mean of all selected model forecasts',
  };

  const handleHorizonChange = (event: any) => {
    const value = event.target.value;
    setLocalHorizon(value);
    dispatch(setSelectedHorizon(value));
  };

  const handleModelsChange = (event: any) => {
    const value = event.target.value as string[];
    setSelectedModels(value);
    if (value[0]) dispatch(setSelectedModel(value[0]));
  };

  const handleGenerateForecast = async () => {
    if (!selectedInstrument) {
      dispatch(setError('Please select an instrument first'));
      return;
    }

    dispatch(setLoading(true));
    dispatch(clearError());

    try {
      const resp = await apiService.trainEnsemble({ symbol: selectedInstrument, horizon: localHorizon, models: selectedModels, windowSize, epochs, includeEnsemble });
      (resp.results || []).forEach((r: any) => {
        if (r.predicted_values) {
          dispatch(addForecast({
            id: r.forecast_id || `${r.model}-${Date.now()}`,
            symbol: resp.symbol,
            horizon: r.horizon || resp.horizon,
            predicted_values: r.predicted_values,
            model_used: r.model,
            timestamp: new Date().toISOString(),
            metrics: r.metrics,
          }));
        }
      });
    } catch (err: any) {
      dispatch(setError(err.response?.data?.error || 'Failed to train models'));
    } finally {
      dispatch(setLoading(false));
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Generate Forecast
        </Typography>
        
        {!selectedInstrument && (
          <Alert severity="info" sx={{ mb: 2 }}>
            Please select an instrument from the list above
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth>
              <InputLabel>Forecast Horizon</InputLabel>
              <Select
                value={localHorizon}
                label="Forecast Horizon"
                onChange={handleHorizonChange}
              >
                {horizonOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={6}>
            <FormControl fullWidth>
              <InputLabel>Models</InputLabel>
              <Select
                multiple
                value={selectedModels}
                label="Models"
                onChange={handleModelsChange}
                renderValue={(sel) => (sel as string[]).join(', ')}
              >
                {modelOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6} sm={3}>
            <TextField label="Window" type="number" value={windowSize} onChange={e=>setWindowSize(parseInt(e.target.value||'48',10))} fullWidth size="small" />
          </Grid>
            <Grid item xs={6} sm={3}>
            <TextField label="Epochs" type="number" value={epochs} onChange={e=>setEpochs(parseInt(e.target.value||'20',10))} fullWidth size="small" />
          </Grid>
            <Grid item xs={12} sm={10}>
              <Box sx={{ display:'flex', alignItems:'center', height:'100%', gap:1 }}>
                <Button variant={includeEnsemble? 'contained':'outlined'} size="small" onClick={()=>setIncludeEnsemble(v=>!v)}>
                  {includeEnsemble? 'Ensemble: ON':'Ensemble: OFF'}
                </Button>
                <Typography variant="caption" color="text.secondary">Toggle inclusion of aggregated ensemble line</Typography>
              </Box>
            </Grid>

          <Grid item xs={12}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <Chip
                label={`Instrument: ${selectedInstrument || 'None'}`}
                color={selectedInstrument ? 'primary' : 'default'}
                variant="outlined"
              />
              <Chip
                label={`Horizon: ${horizonOptions.find(o => o.value === localHorizon)?.label}`}
                color="secondary"
                variant="outlined"
              />
              <Chip
                label={`Models: ${selectedModels.join(', ')}`}
                color="success"
                variant="outlined"
              />
              {includeEnsemble && (
                <Chip label="Ensemble" color="info" variant="outlined" />
              )}
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={{ mt:1 }}>
              <Typography variant="subtitle2" gutterBottom>Model Guide</Typography>
              <Box sx={{ display:'flex', flexWrap:'wrap', gap:1 }}>
                {Object.entries(modelDescriptions).map(([k, desc]) => (
                  <Chip key={k} label={`${k}: ${desc}`} size="small" variant={k==='ENSEMBLE'? 'filled':'outlined'} color={k==='ENSEMBLE'? 'info': 'default'} />
                ))}
              </Box>
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
              <Button
                variant="contained"
                startIcon={loading ? <CircularProgress size={20} /> : <PlayArrow />}
                onClick={handleGenerateForecast}
                disabled={!selectedInstrument || loading}
                fullWidth
              >
                {loading ? 'Generating...' : 'Generate Forecast'}
              </Button>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default ForecastControl;
