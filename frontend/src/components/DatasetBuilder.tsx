import React, { useState } from 'react';
import { Card, CardContent, Typography, Box, TextField, Button, Alert, CircularProgress, FormControlLabel, Switch } from '@mui/material';
import { useAppSelector } from '../hooks/useAppSelector';
import { apiService } from '../services/api';

const DatasetBuilder: React.FC = () => {
  const { selectedInstrument } = useAppSelector((s) => s.instruments);
  const [days, setDays] = useState<number>(90);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<any[]>([]);
  const [files, setFiles] = useState<{ csv?: string; json?: string }>({});
  const [includeNews, setIncludeNews] = useState<boolean>(true);
  const [quick, setQuick] = useState<boolean>(true);

  const handleGenerate = async () => {
    if (!selectedInstrument) {
      setError('Select an instrument first');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await apiService.createDataset(selectedInstrument, days, includeNews && !quick /* skip news if quick */, quick);
      setPreview(res.preview || []);
      setFiles(res.files || {});
    } catch (e: any) {
      const detail = e?.response?.data?.message || e?.response?.data?.error;
      setError(detail || 'Failed to generate dataset');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Dataset Builder
        </Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
          <TextField
            type="number"
            label="Days"
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value || '90', 10))}
            size="small"
          />
          <FormControlLabel control={<Switch checked={includeNews} disabled={quick} onChange={(e) => setIncludeNews(e.target.checked)} />} label="Include News & Sentiment" />
          <FormControlLabel control={<Switch checked={quick} onChange={(e) => setQuick(e.target.checked)} />} label="Quick Mode" />
          <Button variant="contained" onClick={handleGenerate} disabled={!selectedInstrument || loading}>
            {loading ? <CircularProgress size={20} /> : 'Generate Dataset'}
          </Button>
        </Box>
        {!!preview.length && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Preview (last 10 rows)
            </Typography>
            <Box component="pre" sx={{ maxHeight: 240, overflow: 'auto', bgcolor: 'background.default', p: 1, borderRadius: 1 }}>
              {JSON.stringify(preview, null, 2)}
            </Box>
          </Box>
        )}
        {(files.csv || files.json) && (
          <Box sx={{ mt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Saved: {files.csv} {files.json ? `, ${files.json}` : ''}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default DatasetBuilder;


