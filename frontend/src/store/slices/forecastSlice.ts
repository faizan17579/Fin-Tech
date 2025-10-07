import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Forecast {
  id: string;
  symbol: string;
  horizon: number;
  predicted_values: number[];
  model_used: string;
  timestamp: string;
  metrics?: {
    rmse?: number;
    mae?: number;
    mape?: number;
  };
}

export interface ModelPerformance {
  model: string;
  metrics: {
    rmse?: number;
    mae?: number;
    mape?: number;
  };
}

interface ForecastState {
  forecasts: Forecast[];
  modelPerformance: ModelPerformance[];
  loading: boolean;
  error: string | null;
  selectedHorizon: number;
  selectedModel: string;
}

const initialState: ForecastState = {
  forecasts: [],
  modelPerformance: [],
  loading: false,
  error: null,
  selectedHorizon: 7,
  selectedModel: 'baseline',
};

const forecastSlice = createSlice({
  name: 'forecast',
  initialState,
  reducers: {
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setForecasts: (state, action: PayloadAction<Forecast[]>) => {
      state.forecasts = action.payload;
      state.loading = false;
      state.error = null;
    },
    addForecast: (state, action: PayloadAction<Forecast>) => {
      state.forecasts.unshift(action.payload);
    },
    setModelPerformance: (state, action: PayloadAction<ModelPerformance[]>) => {
      state.modelPerformance = action.payload;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.loading = false;
    },
    setSelectedHorizon: (state, action: PayloadAction<number>) => {
      state.selectedHorizon = action.payload;
    },
    setSelectedModel: (state, action: PayloadAction<string>) => {
      state.selectedModel = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
});

export const {
  setLoading,
  setForecasts,
  addForecast,
  setModelPerformance,
  setError,
  setSelectedHorizon,
  setSelectedModel,
  clearError,
} = forecastSlice.actions;

export default forecastSlice.reducer;
