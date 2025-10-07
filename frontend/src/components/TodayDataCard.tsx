import React, { useEffect, useState } from 'react';
import { Card, CardContent, Typography, Box, Chip, CircularProgress, Divider, Button } from '@mui/material';
import { apiService } from '../services/api';
import { useAppSelector } from '../hooks/useAppSelector';

interface OHLCRow {
  timestamp?: string;
  date?: string;
  open?: number; high?: number; low?: number; close?: number; volume?: number;
  Open?: number; High?: number; Low?: number; Close?: number; Volume?: number;
}

const TodayDataCard: React.FC = () => {
  const symbol = useAppSelector(s => s.instruments.selectedInstrument);
  const [loading, setLoading] = useState(false);
  const [row, setRow] = useState<OHLCRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;
    const fetchData = async () => {
      setLoading(true); setError(null);
      try {
        // Try fast latest endpoint first
        let latest: any = null;
        try {
            latest = await apiService.getLatestData(symbol);
        } catch (e) {
            // ignore -> fallback
        }
        if (latest) {
          setRow({
            timestamp: latest.timestamp,
            open: latest.open,
            high: latest.high,
            low: latest.low,
            close: latest.close,
            volume: latest.volume,
          });
        } else {
          const data = await apiService.getHistoricalData(symbol);
          if (Array.isArray(data) && data.length) {
            const lr = data[data.length - 1];
            setRow(lr);
          } else {
            setRow(null);
          }
        }
      } catch (e) {
        console.error(e);
        setError('Failed to load latest data');
      } finally { setLoading(false); }
    };
    fetchData();
  }, [symbol]);

  if (!symbol) return null;

  const getVal = (k: string) => (row as any)?.[k];
  const open = getVal('open') ?? getVal('Open');
  const high = getVal('high') ?? getVal('High');
  const low = getVal('low') ?? getVal('Low');
  const close = getVal('close') ?? getVal('Close');
  const volume = getVal('volume') ?? getVal('Volume');
  const ts = row?.timestamp || row?.date || (row as any)?.Date;
  const change = close && open ? close - open : undefined;
  const changePct = change && open ? (change / open) * 100 : undefined;

  return (
    <Card sx={{ backdropFilter: 'blur(6px)', background: 'rgba(255,255,255,0.6)', position: 'relative' }}>
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
          <Typography variant="h6" fontWeight={600}>Today Overview</Typography>
          <Chip label={symbol} color="primary" size="small" />
        </Box>
        <Divider sx={{ mb: 2 }} />
        {loading && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CircularProgress size={18} /> <Typography variant="body2">Loading latest...</Typography>
          </Box>
        )}
        {error && <Typography variant="body2" color="error">{error}</Typography>}
        {!loading && !error && row && (
          <Box className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <Metric label="Open" value={open} />
            <Metric label="High" value={high} />
            <Metric label="Low" value={low} />
            <Metric label="Close" value={close} />
            <Metric label="Volume" value={volume} format={v => v?.toLocaleString()} />
            <Metric label="Change" value={change} extra={changePct ? `${changePct > 0 ? '+' : ''}${changePct.toFixed(2)}%` : undefined} colored />
          </Box>
        )}
        {!loading && !error && !row && (
          <Typography variant="body2" color="text.secondary">No data available.</Typography>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2 }}>Last record date: {ts || 'N/A'}</Typography>
      </CardContent>
    </Card>
  );
};

const Metric: React.FC<{ label: string; value: number | undefined; extra?: string; format?: (v: number | undefined) => any; colored?: boolean; }> = ({ label, value, extra, format, colored }) => {
  const display = format ? format(value) : (value !== undefined ? value.toFixed(2) : '—');
  let color: any = undefined;
  if (colored && typeof value === 'number') {
    color = value >= 0 ? 'success.main' : 'error.main';
  }
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="subtitle1" fontWeight={600} color={color}>{display}</Typography>
      {extra && <Typography variant="caption" color={color}>{extra}</Typography>}
    </Box>
  );
};

export default TodayDataCard;
