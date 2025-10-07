import React, { useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Grid,
  Alert,
  CircularProgress,
} from '@mui/material';
import { TrendingUp, TrendingDown, Speed } from '@mui/icons-material';
import { useAppSelector } from '../hooks/useAppSelector';
import { useAppDispatch } from '../hooks/useAppDispatch';
import { setModelPerformance, setLoading, setError, clearError } from '../store/slices/forecastSlice';
import { apiService } from '../services/api';

const ModelComparison: React.FC = () => {
  const dispatch = useAppDispatch();
  const { modelPerformance, loading, error } = useAppSelector((state) => state.forecast);

  useEffect(() => {
    fetchModelPerformance();
  }, []);

  const fetchModelPerformance = async () => {
    dispatch(setLoading(true));
    dispatch(clearError());

    try {
      const response = await apiService.getModelPerformance();
      dispatch(setModelPerformance(response));
    } catch (err: any) {
      dispatch(setError(err.response?.data?.error || 'Failed to fetch model performance'));
    } finally {
      dispatch(setLoading(false));
    }
  };

  const getPerformanceColor = (value: number, type: 'rmse' | 'mae' | 'mape') => {
    if (type === 'mape') {
      if (value < 5) return 'success';
      if (value < 15) return 'warning';
      return 'error';
    } else {
      if (value < 1) return 'success';
      if (value < 5) return 'warning';
      return 'error';
    }
  };

  const getPerformanceIcon = (value: number, type: 'rmse' | 'mae' | 'mape') => {
    if (type === 'mape') {
      return value < 10 ? <TrendingUp color="success" /> : <TrendingDown color="error" />;
    } else {
      return value < 2 ? <TrendingUp color="success" /> : <TrendingDown color="error" />;
    }
  };

  const formatValue = (value: number, type: 'rmse' | 'mae' | 'mape') => {
    if (type === 'mape') {
      return `${value.toFixed(2)}%`;
    } else {
      return value.toFixed(4);
    }
  };

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

  if (!modelPerformance.length) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="body1" color="text.secondary">
              No model performance data available
            </Typography>
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Model Performance Comparison
        </Typography>
        
        <TableContainer component={Paper} variant="outlined">
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Model</TableCell>
                <TableCell align="center">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                    <Speed fontSize="small" />
                    RMSE
                  </Box>
                </TableCell>
                <TableCell align="center">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                    <TrendingUp fontSize="small" />
                    MAE
                  </Box>
                </TableCell>
                <TableCell align="center">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                    <TrendingDown fontSize="small" />
                    MAPE
                  </Box>
                </TableCell>
                <TableCell align="center">Overall Score</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {modelPerformance.map((model, index) => {
                const metrics = model.metrics || {};
                const rmse = metrics.rmse || 0;
                const mae = metrics.mae || 0;
                const mape = metrics.mape || 0;
                
                // Calculate overall score (lower is better)
                const overallScore = (rmse + mae + mape / 100) / 3;
                
                return (
                  <TableRow key={model.model || index}>
                    <TableCell>
                      <Chip
                        label={model.model || 'Unknown'}
                        color="primary"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                        {getPerformanceIcon(rmse, 'rmse')}
                        <Chip
                          label={formatValue(rmse, 'rmse')}
                          color={getPerformanceColor(rmse, 'rmse') as any}
                          size="small"
                        />
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                        {getPerformanceIcon(mae, 'mae')}
                        <Chip
                          label={formatValue(mae, 'mae')}
                          color={getPerformanceColor(mae, 'mae') as any}
                          size="small"
                        />
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.5 }}>
                        {getPerformanceIcon(mape, 'mape')}
                        <Chip
                          label={formatValue(mape, 'mape')}
                          color={getPerformanceColor(mape, 'mape') as any}
                          size="small"
                        />
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={overallScore.toFixed(3)}
                        color={overallScore < 1 ? 'success' : overallScore < 3 ? 'warning' : 'error'}
                        variant="filled"
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>

        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            <strong>Legend:</strong> Lower values indicate better performance. 
            Green = Excellent, Yellow = Good, Red = Needs Improvement
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
};

export default ModelComparison;
