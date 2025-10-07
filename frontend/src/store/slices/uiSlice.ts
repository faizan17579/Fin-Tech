import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type UIStage = 'landing' | 'dataset' | 'forecast';

interface UIState {
  stage: UIStage;
}

const initialState: UIState = {
  stage: 'landing',
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setStage: (state, action: PayloadAction<UIStage>) => {
      state.stage = action.payload;
    },
    resetFlow: (state) => {
      state.stage = 'landing';
    }
  }
});

export const { setStage, resetFlow } = uiSlice.actions;
export default uiSlice.reducer;
