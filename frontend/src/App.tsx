import React from 'react'
import { Provider } from 'react-redux'
import { store } from './store'
import { CssBaseline, Container, ThemeProvider, createTheme, AppBar, Toolbar, Typography, IconButton, Grid, Box, Button, Stack } from '@mui/material'
import Brightness4Icon from '@mui/icons-material/Brightness4'
import Brightness7Icon from '@mui/icons-material/Brightness7'
import CandlestickChart from './components/CandlestickChart'
import ForecastControl from './components/ForecastControl'
import ModelComparison from './components/ModelComparison'
import DatasetBuilder from './components/DatasetBuilder'
import Dashboard from './components/Dashboard'
import LandingPage from './components/LandingPage'
import TodayDataCard from './components/TodayDataCard'
import { useAppSelector } from './hooks/useAppSelector'
import { useAppDispatch } from './hooks/useAppDispatch'
import { toggleTheme } from './store/slices/themeSlice'
import { setStage } from './store/slices/uiSlice'
import { setSelectedInstrument } from './store/slices/instrumentsSlice'

const ThemedApp: React.FC = () => {
  const mode = useAppSelector((s) => s.theme.mode)
  const selectedInstrument = useAppSelector((s) => s.instruments.selectedInstrument)
  const stage = useAppSelector(s => s.ui.stage)
  const dispatch = useAppDispatch()
  const theme = React.useMemo(() => createTheme({ palette: { mode } }), [mode])

  // Advance to dataset stage automatically when an instrument is first selected while on landing
  React.useEffect(() => {
    if (selectedInstrument && stage === 'landing') {
      dispatch(setStage('dataset'))
    }
  }, [selectedInstrument, stage, dispatch])

  const handleChangeInstrument = () => {
    dispatch(setSelectedInstrument(null as any))
    dispatch(setStage('landing'))
  }

  const showLanding = stage === 'landing'
  const showDataset = stage === 'dataset' && selectedInstrument
  const showForecast = stage === 'forecast' && selectedInstrument

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppBar position="sticky" color="primary">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>Financial Forecasting</Typography>
          {selectedInstrument && stage !== 'landing' && (
            <Button color='inherit' onClick={handleChangeInstrument} sx={{ mr: 2 }}>Change Instrument</Button>
          )}
          <IconButton color="inherit" onClick={() => dispatch(toggleTheme())}>
            {mode === 'dark' ? <Brightness7Icon /> : <Brightness4Icon />}
          </IconButton>
        </Toolbar>
      </AppBar>

      {showLanding && (
        <Box sx={{ px: { xs: 2, md: 0 }, transition: 'opacity .5s ease', opacity: showLanding ? 1 : 0 }}>
          <LandingPage />
        </Box>
      )}

      {showDataset && (
        <Container sx={{ py: 4 }}>
          <Stack spacing={4}>
            <TodayDataCard />
            <DatasetBuilder />
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 2 }}>
              <Button variant='contained' color='primary' onClick={() => dispatch(setStage('forecast'))}>Go to Forecasting</Button>
            </Box>
          </Stack>
        </Container>
      )}

      {showForecast && (
        <Container sx={{ py: 3, animation: 'fadeSlideIn 0.6s ease' }}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <CandlestickChart />
            </Grid>
            <Grid item xs={12} md={4}>
              <ForecastControl />
            </Grid>
            <Grid item xs={12}>
              <ModelComparison />
            </Grid>
            <Grid item xs={12}>
              <Dashboard />
            </Grid>
            <Grid item xs={12}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 2 }}>
                <Button variant='outlined' onClick={() => dispatch(setStage('dataset'))}>Back to Dataset</Button>
              </Box>
            </Grid>
          </Grid>
        </Container>
      )}
    </ThemeProvider>
  )
}

const App: React.FC = () => (
  <Provider store={store}>
    <ThemedApp />
  </Provider>
)

export default App


