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
  FormGroup,
  FormControlLabel,
  Checkbox,
} from '@mui/material';
import { apiService } from '../services/api';
import { useAppSelector } from '../hooks/useAppSelector';

const modelOptions = [
  { value: 'ARIMA', label: 'ARIMA' },
  { value: 'HoltWinters', label: 'Holt-Winters' },
  { value: 'SMA20', label: 'SMA (20)' },
  { value: 'EMA20', label: 'EMA (20)' },
  { value: 'WMA20', label: 'WMA (20)' },
  { value: 'LSTM', label: 'LSTM' },
];

const InstrumentDetail: React.FC = () => {
  const { selectedInstrument } = useAppSelector((s) => s.instruments);
  const [horizon, setHorizon] = useState<number>(24);
  const [windowSize, setWindowSize] = useState<number>(48);
  const [selectedModels, setSelectedModels] = useState<string[]>(['ARIMA', 'LSTM']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<any[] | null>(null);

  const toggleModel = (mv: string) => {
    setSelectedModels((prev) => (prev.includes(mv) ? prev.filter((p) => p !== mv) : [...prev, mv]));
  };

  const handleTrain = async () => {
    setError(null);
    if (!selectedInstrument) {
      setError('Select an instrument first');
      return;
    }
    if (selectedModels.length === 0) {
      setError('Select at least one model');
      return;
    }
    setLoading(true);
    try {
      const resp = await apiService.trainModels(selectedInstrument, selectedModels, horizon, windowSize);
      // backend returns results array in current implementation
      setResults(resp.results || [resp]);
    } catch (err: any) {
      setError(err?.response?.data?.error || err?.message || 'Training failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Instrument — {selectedInstrument || 'None'}
        </Typography>

        {!selectedInstrument && (
          <Alert severity="info">Please choose an instrument from the selector above to manage training and view details.</Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ my: 1 }}>{error}</Alert>
        )}

        <Grid container spacing={2} sx={{ mt: 0.5 }}>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Horizon (hours)"
              type="number"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              fullWidth
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Window Size"
              type="number"
              value={windowSize}
              onChange={(e) => setWindowSize(Number(e.target.value))}
              fullWidth
            />
          </Grid>

          <Grid item xs={12}>
            <Typography variant="subtitle2" gutterBottom>Models to train</Typography>
            <FormGroup row>
              {modelOptions.map((m) => (
                <FormControlLabel
                  key={m.value}
                  control={<Checkbox checked={selectedModels.includes(m.value)} onChange={() => toggleModel(m.value)} />}
                  label={m.label}
                />
              ))}
            </FormGroup>
          </Grid>

          <Grid item xs={12}>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="contained" onClick={handleTrain} disabled={loading || !selectedInstrument} startIcon={loading ? <CircularProgress size={18} /> : undefined}>
                {loading ? 'Training...' : 'Train Models'}
              </Button>
              <Button variant="outlined" onClick={() => { setResults(null); setError(null); }}>
                Reset
              </Button>
            </Box>
          </Grid>

          <Grid item xs={12}>
            {results && (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Typography variant="subtitle1">Results</Typography>
                {results.map((r: any, idx: number) => (
                  <Box key={idx} sx={{ p: 1, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}>
                    <Typography variant="body2"><strong>Model:</strong> {r.model || r.model_name || 'unknown'}</Typography>
                    <Typography variant="body2"><strong>Metrics:</strong> {r.rmse ? `RMSE ${r.rmse.toFixed(3)}` : ''} {r.mape ? `MAPE ${r.mape?.toFixed(2)}%` : ''}</Typography>
                  </Box>
                ))}
              </Box>
            )}
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

export default InstrumentDetail;
