import { io, Socket } from 'socket.io-client';
import { store } from '../store';
import { updateLivePrice, setConnected } from '../store/slices/liveDataSlice';

class WebSocketService {
  private socket: Socket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  connect() {
    if (this.socket?.connected) {
      return;
    }

    this.socket = io('/', {
      transports: ['websocket'],
      timeout: 20000,
    });

    this.socket.on('connect', () => {
      console.log('WebSocket connected');
      store.dispatch(setConnected(true));
      this.reconnectAttempts = 0;
    });

    this.socket.on('disconnect', () => {
      console.log('WebSocket disconnected');
      store.dispatch(setConnected(false));
    });

    this.socket.on('connect_error', (error) => {
      console.error('WebSocket connection error:', error);
      store.dispatch(setConnected(false));
      this.handleReconnect();
    });

    this.socket.on('price_update', (data: { symbol: string; price: number; timestamp: string }) => {
      store.dispatch(updateLivePrice({
        symbol: data.symbol,
        price: data.price,
        timestamp: data.timestamp,
      }));
    });

    this.socket.on('subscribed', (data: { symbol: string }) => {
      console.log(`Subscribed to ${data.symbol}`);
    });

    this.socket.on('unsubscribed', (data: { symbol: string }) => {
      console.log(`Unsubscribed from ${data.symbol}`);
    });

    this.socket.on('error', (error: { message: string }) => {
      console.error('WebSocket error:', error.message);
    });
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      store.dispatch(setConnected(false));
    }
  }

  subscribeToPrice(symbol: string) {
    if (this.socket?.connected) {
      this.socket.emit('subscribe_price', { symbol });
    }
  }

  unsubscribeFromPrice(symbol: string) {
    if (this.socket?.connected) {
      this.socket.emit('unsubscribe_price', { symbol });
    }
  }

  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
      console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts})`);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('Max reconnection attempts reached');
    }
  }

  isConnected(): boolean {
    return this.socket?.connected || false;
  }
}

export const webSocketService = new WebSocketService();
export default webSocketService;
