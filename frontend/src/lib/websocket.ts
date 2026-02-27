const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:4000';

type EventHandler = (data: any) => void;

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private handlers = new Map<string, Set<EventHandler>>();
  private token: string | null = null;
  private isConnecting = false;

  connect(token: string) {
    if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) return;
    this.token = token;
    this.isConnecting = true;

    try {
      // D3 fix: Don't send JWT in URL (visible in logs/proxies).
      // Connect without token, then authenticate via first message.
      this.ws = new WebSocket(`${WS_URL}/ws`);

      this.ws.onopen = () => {
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        // Send auth message immediately after connection
        this.send('auth', { token });
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.emit(message.event, message.data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      this.ws.onclose = (event) => {
        this.isConnecting = false;
        this.emit('disconnected', { code: event.code, reason: event.reason });

        if (event.code !== 4001 && this.reconnectAttempts < this.maxReconnectAttempts) {
          setTimeout(() => {
            this.reconnectAttempts++;
            if (this.token) this.connect(this.token);
          }, this.reconnectDelay * Math.pow(2, this.reconnectAttempts));
        }
      };

      this.ws.onerror = () => {
        this.isConnecting = false;
        this.emit('error', { message: 'WebSocket error' });
      };
    } catch (e) {
      this.isConnecting = false;
    }
  }

  disconnect() {
    this.token = null;
    this.reconnectAttempts = this.maxReconnectAttempts;
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(event: string, data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data, timestamp: new Date().toISOString() }));
    }
  }

  subscribeSession(sessionId: string) {
    this.send('subscribe_session', { sessionId });
  }

  unsubscribeSession(sessionId: string) {
    this.send('unsubscribe_session', { sessionId });
  }

  startExecution(sessionId: string) {
    this.send('start_execution', { sessionId });
  }

  pauseExecution(sessionId: string) {
    this.send('pause_execution', { sessionId });
  }

  cancelExecution(sessionId: string) {
    this.send('cancel_execution', { sessionId });
  }

  sendUserInput(sessionId: string, input: string) {
    this.send('user_input', { sessionId, input });
  }

  on(event: string, handler: EventHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => this.off(event, handler);
  }

  off(event: string, handler: EventHandler) {
    this.handlers.get(event)?.delete(handler);
  }

  private emit(event: string, data: any) {
    this.handlers.get(event)?.forEach((handler) => handler(data));
    this.handlers.get('*')?.forEach((handler) => handler({ event, data }));
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export const wsClient = new WebSocketClient();
