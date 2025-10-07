import axios, { AxiosInstance, AxiosResponse } from 'axios';

class ApiService {
  private api: AxiosInstance;

  constructor() {
    this.api = axios.create({
      baseURL: '/api',
      // Increase default timeout to accommodate slower model runs
      timeout: 60000,
    });
  }

  // Authentication removed - endpoints now accessible without JWT

  // Instruments endpoints
  async getInstruments(): Promise<{ 
    stocks: Array<{symbol: string; name: string; sector: string}>; 
    crypto: Array<{symbol: string; name: string; sector: string}>; 
    forex: Array<{symbol: string; name: string; sector: string}> 
  }> {
    const response = await this.api.get('/instruments');
    return response.data;
  }

  async searchInstruments(query: string): Promise<any[]> {
    if (!query.trim()) return [];
    const response = await this.api.get(`/instruments/search?q=${encodeURIComponent(query)}`);
    return response.data;
  }

  async getHistoricalData(symbol: string): Promise<any[]> {
    const response = await this.api.get(`/historical/${symbol}`);
    return response.data;
  }

  // Forecast endpoints
  async createForecast(symbol: string, horizon: number, modelType: string = 'baseline'): Promise<any> {
    // Use a longer timeout for forecast requests; LSTM/ARIMA can take >10s
    const response = await this.api.post(
      '/forecast',
      {
        symbol,
        horizon,
        model_type: modelType,
      },
      {
        timeout: 120000,
      }
    );
    return response.data;
  }

  async getForecast(forecastId: string): Promise<any> {
    const response = await this.api.get(`/forecast/${forecastId}`);
    return response.data;
  }

  async getModelPerformance(): Promise<any[]> {
    const response = await this.api.get('/models/performance');
    return response.data;
  }

  // Live price endpoint
  async getLivePrice(symbol: string): Promise<{ symbol: string; price: number }> {
    const response = await this.api.get(`/live-price/${symbol}`);
    return response.data;
  }

  async getQuotes(symbols: string[]): Promise<Array<{ symbol: string; price: number | null }>> {
    const response = await this.api.get(`/quotes?symbols=${encodeURIComponent(symbols.join(','))}`);
    return response.data;
  }

  async createDataset(symbol: string, days: number, includeNews?: boolean, quick: boolean = false): Promise<any> {
    const response = await this.api.post('/dataset', { symbol, days, include_news: !!includeNews, quick });
    return response.data;
  }

  async trainModels(symbol: string, models: string[], horizon: number, windowSize: number): Promise<any> {
    const response = await this.api.post('/train', { symbol, models, horizon, window_size: windowSize }, { timeout: 180000 });
    return response.data;
  }

  async trainEnsemble(params: { symbol: string; horizon: number; models: string[]; windowSize?: number; epochs?: number; includeEnsemble?: boolean }): Promise<any> {
    const { symbol, horizon, models, windowSize = 48, epochs = 20, includeEnsemble = true } = params;
    const response = await this.api.post('/train-ensemble', { symbol, horizon, models, window_size: windowSize, epochs, include_ensemble: includeEnsemble }, { timeout: 240000 });
    return response.data;
  }

  async getLatestData(symbol: string): Promise<{ symbol: string; timestamp: string; open: number; high: number; low: number; close: number; volume: number }> {
    const response = await this.api.get(`/latest/${symbol}`);
    return response.data;
  }
}

export const apiService = new ApiService();
export default apiService;
