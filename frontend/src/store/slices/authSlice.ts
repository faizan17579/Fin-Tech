import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface AuthState {
  isAuthenticated: boolean;
  token: string | null;
  user: string | null;
  loading: boolean;
  error: string | null;
}

// Authentication disabled - all endpoints are now public
const initialState: AuthState = {
  isAuthenticated: true, // Always authenticated since auth is removed
  token: null,
  user: 'Public User',
  loading: false,
  error: null,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    // Authentication methods disabled - all endpoints are public
    clearError: (state) => {
      state.error = null;
    },
    // Keep minimal structure for compatibility
    setUser: (state, action: PayloadAction<string>) => {
      state.user = action.payload;
    },
  },
});

export const { clearError, setUser } = authSlice.actions;
export default authSlice.reducer;
