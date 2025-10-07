import React, { useEffect, useState, useMemo } from 'react';
import { Box, Typography, Button, Card, CardContent, Grid, Chip, Divider, useTheme, CircularProgress } from '@mui/material';
import InstrumentSelector from './InstrumentSelector';
import { useAppSelector } from '../hooks/useAppSelector';
import { useAppDispatch } from '../hooks/useAppDispatch';
import { setSelectedInstrument } from '../store/slices/instrumentsSlice';
import { apiService } from '../services/api';

interface Quote { symbol: string; price: number | null }

// Famous symbols to show on landing page (mix of stocks + crypto)
const FAMOUS_SYMBOLS = [
  'AAPL','MSFT','GOOG','AMZN','TSLA','NVDA','META','JPM','BTC-USD','ETH-USD','EURUSD=X','GBPUSD=X'
];

const REFRESH_INTERVAL = 15000; // 15s for quotes refresh

const LandingPage: React.FC = () => {
  const theme = useTheme();
  const dispatch = useAppDispatch();
  const selectedInstrument = useAppSelector(s => s.instruments.selectedInstrument);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);

  const gradientBg = useMemo(() => (
    theme.palette.mode === 'dark'
      ? 'bg-gradient-to-br from-slate-900 via-slate-800 to-slate-700'
      : 'bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50'
  ), [theme.palette.mode]);

  const fetchQuotes = async () => {
    try {
      const data = await apiService.getQuotes(FAMOUS_SYMBOLS);
      setQuotes(data);
    } catch (e) {
      console.error('Failed to fetch quotes', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuotes();
    const id = setInterval(fetchQuotes, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, []);

  const handleSelect = (sym: string) => {
    dispatch(setSelectedInstrument(sym));
  };

  // If user already picked an instrument, this page should not render
  if (selectedInstrument) return null;

  return (
    <div className={`relative min-h-[calc(100vh-64px)] flex flex-col ${gradientBg} overflow-hidden landing-grid-pattern`}>
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute inset-0 opacity-30 mix-blend-overlay bg-[radial-gradient(circle_at_20%_30%,rgba(255,255,255,0.5),transparent_60%),radial-gradient(circle_at_80%_70%,rgba(255,255,255,0.4),transparent_65%)] animate-pulse" />
      </div>

      {/* Hero Section */}
      <section className="relative z-10 text-center px-4 pt-12 md:pt-20 max-w-5xl mx-auto animate-[fadeSlideIn_1s_ease_forwards] opacity-0">
        <h1 className="font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-400 text-4xl md:text-6xl mb-4">
          Intelligent Financial Forecasting
        </h1>
        <p className="text-slate-600 dark:text-slate-300 text-lg md:text-xl max-w-3xl mx-auto mb-6">
          Explore real-time market data, build enriched datasets, and generate predictive models across stocks, crypto, and forex.
        </p>
        <div className="flex justify-center">
          <Button variant="contained" size="large" onClick={() => handleSelect('AAPL')} className="animate-[popIn_1.2s_ease_forwards] opacity-0">
            Get Started
          </Button>
        </div>
      </section>

      {/* Scrolling Ticker */}
      <div className="relative z-10 px-4 mt-8">
        <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white/60 dark:bg-slate-900/40 backdrop-blur py-2 overflow-hidden">
          <div className="flex gap-8 whitespace-nowrap animate-[tickerScroll_40s_linear_infinite]">
            {(loading ? FAMOUS_SYMBOLS.map(s => ({ symbol: s, price: null })) : quotes).map(q => (
              <div key={q.symbol} onClick={() => handleSelect(q.symbol)} className="flex items-center gap-2 px-2 cursor-pointer transition-transform hover:scale-105">
                <span className="text-xs font-semibold px-2 py-1 rounded bg-indigo-600 text-white dark:bg-indigo-500">{q.symbol}</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">{q.price === null ? '—' : `$${q.price.toFixed(2)}`}</span>
              </div>
            ))}
            {/* Duplicate for seamless loop */}
            {(loading ? FAMOUS_SYMBOLS.map(s => ({ symbol: s, price: null })) : quotes).map(q => (
              <div key={q.symbol + '_dup'} onClick={() => handleSelect(q.symbol)} className="flex items-center gap-2 px-2 cursor-pointer transition-transform hover:scale-105">
                <span className="text-xs font-semibold px-2 py-1 rounded bg-indigo-600 text-white dark:bg-indigo-500">{q.symbol}</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">{q.price === null ? '—' : `$${q.price.toFixed(2)}`}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="relative z-10 px-4 md:px-12 mt-12 pb-20">
        <Grid container spacing={4}>
          <Grid item xs={12} md={7} className="animate-[fadeUp_1.2s_.2s_ease_forwards] opacity-0">
            <Card sx={{ backdropFilter: 'blur(8px)', background: theme.palette.mode === 'dark' ? 'rgba(15,23,42,0.6)' : 'rgba(255,255,255,0.8)' }}>
              <CardContent>
                <Typography variant="h5" fontWeight={600} gutterBottom>Platform Overview</Typography>
                <Divider sx={{ mb: 2 }} />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[{
                    title: 'Real-time Data', desc: 'Stream live prices via WebSockets.'
                  }, {
                    title: 'Forecast Models', desc: 'Baseline, ARIMA, LSTM comparisons.'
                  }, {
                    title: 'Dataset Builder', desc: 'Create enriched time-series sets.'
                  }, {
                    title: 'Multi-Asset', desc: 'Equities, crypto & major forex.'
                  }].map((f, idx) => (
                    <div key={f.title} className="p-4 rounded-xl bg-slate-100/70 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 shadow-sm backdrop-blur-sm opacity-0 animate-[featureCard_1s_ease_forwards]" style={{ animationDelay: `${(idx * 0.15) + 0.3}s` }}>
                      <div className="font-semibold text-slate-800 dark:text-slate-100 mb-1">{f.title}</div>
                      <div className="text-sm text-slate-600 dark:text-slate-300 leading-snug">{f.desc}</div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={5} className="animate-[fadeUp_1.2s_.4s_ease_forwards] opacity-0">
            <Card sx={{ height: '100%', backdropFilter: 'blur(8px)', background: theme.palette.mode === 'dark' ? 'rgba(15,23,42,0.55)' : 'rgba(255,255,255,0.9)' }}>
              <CardContent>
                <Typography variant="h5" fontWeight={600} gutterBottom>Select an Instrument</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Choose a symbol to unlock the analytics dashboard.
                </Typography>
                <div className="max-h-[420px] overflow-y-visible pr-2 landing-scrollbar">
                  <InstrumentSelector compact />
                </div>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </div>

      {/* Loading overlay optional */}
      {loading && (
        <Box sx={{ position: 'absolute', top: 8, right: 16, display: 'flex', alignItems: 'center', gap: 1, zIndex: 20 }}>
          <CircularProgress size={18} />
          <Typography variant="caption" color="text.secondary">Loading quotes...</Typography>
        </Box>
      )}
    </div>
  );
};

export default LandingPage;
