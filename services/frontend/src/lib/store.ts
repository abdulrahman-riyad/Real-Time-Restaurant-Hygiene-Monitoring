import { create } from 'zustand'
import toast from 'react-hot-toast'

export interface Violation {
  id: string;
  type: string;
  severity: string;
  confidence: number;
  timestamp: number;
  frame_id: string;
  person_id: string;
  message: string;
  stream_id?: string;
  location?: { x: number; y: number };
  bbox?: { x1: number; y1: number; x2: number; y2: number };
}

interface StreamData {
  stream_id: string;
  data: {
    annotated_frame_data: string;
  };
  stats: {
    fps: number;
    violations_count: number;
  };
}

interface Store {
  socket: WebSocket | null;
  isConnected: boolean;
  streams: Map<string, StreamData>;
  violations: Violation[];
  initializeConnection: () => void;
  subscribeToStream: (streamId: string) => void;
  unsubscribeFromStream: (streamId: string) => void;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

export const useStore = create<Store>((set, get) => ({
  socket: null,
  isConnected: false,
  streams: new Map(),
  violations: [],

  initializeConnection: () => {
    if (get().socket) {
      return;
    }

    const socket = new WebSocket(WS_URL);
    set({ socket });

    socket.onopen = () => {
      console.log('WebSocket connection established.');
      set({ isConnected: true });
      toast.success('Connected to monitoring system');
    };

    socket.onclose = () => {
      console.log('WebSocket disconnected.');
      set({ isConnected: false, socket: null });
      toast.error('Disconnected. Reconnecting in 3s...');
      setTimeout(() => get().initializeConnection(), 3000);
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      socket.close();
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        switch (message.type) {
          case 'detection_results':
            set((state) => ({
              streams: new Map(state.streams).set(message.stream_id, message),
            }));
            break;
          case 'violation_alert':
            const violation: Violation = message.data;
            toast.error(`VIOLATION: ${violation.message}`, { duration: 5000, icon: '⚠️' });
            set((state) => ({
              violations: [violation, ...state.violations].slice(0, 50),
            }));
            break;
        }
      } catch (error) {
        console.error('Error parsing incoming message:', error);
      }
    };
  },

  subscribeToStream: (streamId: string) => {
    const { socket } = get();
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'subscribe', stream_id: streamId }));
    }
  },

  unsubscribeFromStream: (streamId: string) => {
    const { socket } = get();
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'unsubscribe', stream_id: streamId }));
    }
  },
}));