import { configureStore } from '@reduxjs/toolkit';
import authSlice from './slices/authSlice';
import instrumentsSlice from './slices/instrumentsSlice';
import forecastSlice from './slices/forecastSlice';
import themeSlice from './slices/themeSlice';
import liveDataSlice from './slices/liveDataSlice';
import uiSlice from './slices/uiSlice';

export const store = configureStore({
  reducer: {
    auth: authSlice,
    instruments: instrumentsSlice,
    forecast: forecastSlice,
    theme: themeSlice,
    liveData: liveDataSlice,
    ui: uiSlice,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
