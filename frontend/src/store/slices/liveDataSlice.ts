import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface LivePrice {
  symbol: string;
  price: number;
  timestamp: string;
}

interface LiveDataState {
  livePrices: Record<string, LivePrice>;
  connected: boolean;
  subscribedSymbols: string[];
}

const initialState: LiveDataState = {
  livePrices: {},
  connected: false,
  subscribedSymbols: [],
};

const liveDataSlice = createSlice({
  name: 'liveData',
  initialState,
  reducers: {
    setConnected: (state, action: PayloadAction<boolean>) => {
      state.connected = action.payload;
    },
    updateLivePrice: (state, action: PayloadAction<LivePrice>) => {
      state.livePrices[action.payload.symbol] = action.payload;
    },
    addSubscribedSymbol: (state, action: PayloadAction<string>) => {
      if (!state.subscribedSymbols.includes(action.payload)) {
        state.subscribedSymbols.push(action.payload);
      }
    },
    removeSubscribedSymbol: (state, action: PayloadAction<string>) => {
      state.subscribedSymbols = state.subscribedSymbols.filter(symbol => symbol !== action.payload);
    },
    clearLivePrices: (state) => {
      state.livePrices = {};
    },
  },
});

export const {
  setConnected,
  updateLivePrice,
  addSubscribedSymbol,
  removeSubscribedSymbol,
  clearLivePrices,
} = liveDataSlice.actions;

export default liveDataSlice.reducer;
