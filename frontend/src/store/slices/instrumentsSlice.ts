import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Instrument {
  symbol: string;
  name?: string;
  type: 'stock' | 'crypto' | 'forex';
  price?: number;
  change?: number;
  changePercent?: number;
}

interface InstrumentsState {
  instruments: Instrument[];
  selectedInstrument: string | null;
  loading: boolean;
  error: string | null;
  searchTerm: string;
  filterType: 'all' | 'stock' | 'crypto' | 'forex';
}

const initialState: InstrumentsState = {
  instruments: [],
  selectedInstrument: null,
  loading: false,
  error: null,
  searchTerm: '',
  filterType: 'all',
};

const instrumentsSlice = createSlice({
  name: 'instruments',
  initialState,
  reducers: {
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setInstruments: (state, action: PayloadAction<Instrument[]>) => {
      state.instruments = action.payload;
      state.loading = false;
      state.error = null;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.loading = false;
    },
    setSelectedInstrument: (state, action: PayloadAction<string>) => {
      state.selectedInstrument = action.payload;
    },
    setSearchTerm: (state, action: PayloadAction<string>) => {
      state.searchTerm = action.payload;
    },
    setFilterType: (state, action: PayloadAction<'all' | 'stock' | 'crypto' | 'forex'>) => {
      state.filterType = action.payload;
    },
    updateInstrumentPrice: (state, action: PayloadAction<{ symbol: string; price: number; change: number; changePercent: number }>) => {
      const instrument = state.instruments.find(inst => inst.symbol === action.payload.symbol);
      if (instrument) {
        instrument.price = action.payload.price;
        instrument.change = action.payload.change;
        instrument.changePercent = action.payload.changePercent;
      }
    },
  },
});

export const {
  setLoading,
  setInstruments,
  setError,
  setSelectedInstrument,
  setSearchTerm,
  setFilterType,
  updateInstrumentPrice,
} = instrumentsSlice.actions;

export default instrumentsSlice.reducer;
