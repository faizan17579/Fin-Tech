import React, { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';
import { Box, Card, CardContent, Typography, CircularProgress, Alert } from '@mui/material';
import { useAppSelector } from '../hooks/useAppSelector';
import { apiService } from '../services/api';

interface HistoricalData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const CandlestickChart: React.FC = () => {
  const { selectedInstrument } = useAppSelector((state) => state.instruments);
  const { forecasts } = useAppSelector((state) => state.forecast);
  const [data, setData] = useState<HistoricalData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (selectedInstrument) {
      fetchHistoricalData();
    }
  }, [selectedInstrument]);

  const fetchHistoricalData = async () => {
    if (!selectedInstrument) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiService.getHistoricalData(selectedInstrument);
      setData(response);
    } catch (err) {
      setError('Failed to fetch historical data');
      console.error('Error fetching historical data:', err);
    } finally {
      setLoading(false);
    }
  };

  const prepareCandlestickData = () => {
    if (!data.length) return [];

    const x = data.map((d) => new Date(d.timestamp));
    const open = data.map((d) => d.open);
    const high = data.map((d) => d.high);
    const low = data.map((d) => d.low);
    const close = data.map((d) => d.close);

    return [
      {
        x,
        open,
        high,
        low,
        close,
        type: 'candlestick',
        name: selectedInstrument,
        increasing: { line: { color: '#26a69a' } },
        decreasing: { line: { color: '#ef5350' } },
      },
    ];
  };

  const prepareVolumeData = () => {
    if (!data.length) return [];

    const x = data.map((d) => new Date(d.timestamp));
    const y = data.map((d) => d.volume);
    const colors = data.map((d, i) => 
      i > 0 && d.close > data[i - 1].close ? '#26a69a' : '#ef5350'
    );

    return [
      {
        x,
        y,
        type: 'bar',
        name: 'Volume',
        marker: { color: colors },
        yaxis: 'y2',
      },
    ];
  };

  const layout = {
    title: {
      text: selectedInstrument ? `${selectedInstrument} Price Chart` : 'Select an instrument',
      font: { size: 16 },
    },
    xaxis: {
      type: 'date',
      title: 'Date',
    },
    yaxis: {
      title: 'Price ($)',
      side: 'right',
    },
    yaxis2: {
      title: 'Volume',
      side: 'left',
      overlaying: 'y',
      tickmode: 'auto',
      nticks: 3,
    },
    plot_bgcolor: 'rgba(0,0,0,0)',
    paper_bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#333' },
    margin: { l: 50, r: 50, t: 50, b: 50 },
    showlegend: true,
    dragmode: 'zoom',
    modebar: {
      orientation: 'v',
    },
  };

  const config = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
    responsive: true,
  };

  if (!selectedInstrument) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h6" color="text.secondary">
              Select an instrument to view the price chart
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  if (!data.length) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body1" color="text.secondary">
              No historical data available for {selectedInstrument}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  const candlestickData = prepareCandlestickData();
  const volumeData = prepareVolumeData();
  const forecastOverlays = (() => {
    if (!selectedInstrument || !data.length) return [] as any[];
    const related = forecasts.filter(f => f.symbol === selectedInstrument && f.predicted_values?.length);
    if (!related.length) return [] as any[];
    const lastTs = new Date(data[data.length - 1].timestamp);
    let stepMs = 24 * 3600 * 1000;
    if (data.length >= 2) {
      const t1 = new Date(data[data.length - 1].timestamp).getTime();
      const t0 = new Date(data[data.length - 2].timestamp).getTime();
      const delta = Math.abs(t1 - t0);
      if (delta <= 3 * 3600 * 1000) stepMs = 3600 * 1000;
    }
    const palette: Record<string,string> = {
      SMA: '#8d6e63',
      EMA: '#ffb300',
      ARIMA: '#3949ab',
      LSTM: '#1e88e5',
      ENSEMBLE: '#2e7d32',
    };
    const traces: any[] = [];
    // Show newest first on top
    related.slice(0, 8).forEach(r => {
      const x: Date[] = [];
      for (let i = 1; i <= r.predicted_values.length; i++) {
        x.push(new Date(lastTs.getTime() + i * stepMs));
      }
      const model = (r.model_used || 'MODEL').toUpperCase();
      const isNeural = model.includes('LSTM');
      traces.push({
        x,
        y: r.predicted_values,
        type: 'scatter',
        mode: 'lines',
        name: `${model} (${r.horizon}h)`,
        line: { color: palette[model] || '#1976d2', width: 2, dash: isNeural ? 'solid' : (model==='ENSEMBLE' ? 'dot' : 'dash') },
        hovertemplate: `${model}<br>%{x|%Y-%m-%d %H:%M}<br>Price=%{y:.2f}<extra></extra>`
      });
    });
    return traces;
  })();

  const allData = [...candlestickData, ...volumeData, ...forecastOverlays];

  return (
    <Card>
      <CardContent>
        <Box sx={{ height: 500 }}>
          <Plot
            data={allData}
            layout={layout}
            config={config}
            style={{ width: '100%', height: '100%' }}
            useResizeHandler={true}
          />
        </Box>
      </CardContent>
    </Card>
  );
};

export default CandlestickChart;
