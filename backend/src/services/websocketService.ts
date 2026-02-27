import { Server as HttpServer } from 'http';
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import { logger } from '../utils/logger';
import { executionService } from '../services/executionService';

interface AuthenticatedSocket extends WebSocket {
  userId?: string;
  sessionId?: string;
  isAlive?: boolean;
  isRuntime?: boolean;
}

export class WebSocketService {
  private wss: WebSocketServer;
  private clients = new Map<string, Set<AuthenticatedSocket>>();
  private runtimeConnections = new Map<string, AuthenticatedSocket>();
  private heartbeatInterval: NodeJS.Timeout | null = null;

  constructor(server: HttpServer) {
    this.wss = new WebSocketServer({ server, path: '/ws' });
    this.init();
    logger.info('WebSocket server initialized');
  }

  private init() {
    this.wss.on('connection', (ws: AuthenticatedSocket, req) => {
      this.handleConnection(ws, req);
    });

    // Heartbeat to detect stale connections
    this.heartbeatInterval = setInterval(() => {
      this.wss.clients.forEach((ws: WebSocket) => {
        const socket = ws as AuthenticatedSocket;
        if (socket.isAlive === false) {
          this.removeClient(socket);
          return socket.terminate();
        }
        socket.isAlive = false;
        socket.ping();
      });
    }, 30000);

    this.wss.on('close', () => {
      if (this.heartbeatInterval) {
        clearInterval(this.heartbeatInterval);
      }
    });
  }

  private async handleConnection(ws: AuthenticatedSocket, req: any) {
    // D3 fix: Support both URL-token (legacy) and post-connection auth.
    // Prefer post-connection auth — token in URL is logged by proxies/CDNs.
    const url = new URL(req.url, `http://${req.headers.host}`);
    const urlToken = url.searchParams.get('token');

    if (urlToken) {
      // Legacy path: authenticate immediately from URL token
      this.authenticateSocket(ws, urlToken);
    } else {
      // New path: wait for 'auth' message with token
      ws.isAlive = true;

      // Set a 10s authentication deadline
      const authTimeout = setTimeout(() => {
        if (!ws.userId) {
          ws.close(4001, 'Authentication timeout');
        }
      }, 10000);

      ws.on('message', (data) => {
        const raw = data.toString();
        // If not yet authenticated, expect an auth message first
        if (!ws.userId) {
          try {
            const msg = JSON.parse(raw);
            if (msg.event === 'auth' && msg.data?.token) {
              clearTimeout(authTimeout);
              this.authenticateSocket(ws, msg.data.token);
              return;
            }
          } catch {}
          ws.close(4001, 'Authentication required');
          return;
        }
        this.handleMessage(ws, raw);
      });

      ws.on('pong', () => { ws.isAlive = true; });
      ws.on('close', () => { clearTimeout(authTimeout); this.removeClient(ws); });
      ws.on('error', (error) => { logger.error('WebSocket error:', error); clearTimeout(authTimeout); this.removeClient(ws); });
    }
  }

  private authenticateSocket(ws: AuthenticatedSocket, token: string) {
    try {
      const decoded = jwt.verify(token, config.jwt.secret) as { userId: string };
      ws.userId = decoded.userId;
      ws.isAlive = true;

      ws.on('pong', () => {
        ws.isAlive = true;
      });

      // Remove any pre-auth message handler, add the real one
      ws.removeAllListeners('message');
      ws.on('message', (data) => {
        this.handleMessage(ws, data.toString());
      });

      ws.on('close', () => {
        this.removeClient(ws);
      });

      ws.on('error', (error) => {
        logger.error('WebSocket error:', error);
        this.removeClient(ws);
      });

      ws.send(JSON.stringify({
        event: 'connected',
        data: { userId: ws.userId },
        timestamp: new Date().toISOString(),
      }));

      logger.debug(`WebSocket connected: user ${ws.userId}`);
    } catch (error) {
      ws.close(4001, 'Invalid token');
    }
  }

  private registerRuntime(ws: AuthenticatedSocket) {
    if (!ws.userId) return;
    const existing = this.runtimeConnections.get(ws.userId);
    if (existing && existing !== ws && existing.readyState === WebSocket.OPEN) {
      existing.close(4002, 'Replaced by new runtime connection');
    }
    ws.isRuntime = true;
    this.runtimeConnections.set(ws.userId, ws);
    logger.info(`Runtime registered for user ${ws.userId}`);

    ws.on('close', () => {
      if (this.runtimeConnections.get(ws.userId!) === ws) {
        this.runtimeConnections.delete(ws.userId!);
        logger.info(`Runtime disconnected for user ${ws.userId}`);
      }
    });
  }

  sendToRuntime(userId: string, command: { type: string; [key: string]: any }): boolean {
    const ws = this.runtimeConnections.get(userId);
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      logger.warn(`No runtime connection for user ${userId}`);
      return false;
    }
    ws.send(JSON.stringify({ event: 'runtime_command', data: command, timestamp: new Date().toISOString() }));
    return true;
  }

  isRuntimeConnected(userId: string): boolean {
    const ws = this.runtimeConnections.get(userId);
    return !!(ws && ws.readyState === WebSocket.OPEN);
  }

  private async handleMessage(ws: AuthenticatedSocket, rawMessage: string) {
    try {
      const message = JSON.parse(rawMessage);

      if (message.event === 'runtime_register') {
        this.registerRuntime(ws);
        ws.send(JSON.stringify({ event: 'runtime_registered', data: { userId: ws.userId }, timestamp: new Date().toISOString() }));
        return;
      }

      switch (message.event) {
        case 'subscribe_session':
          this.subscribeToSession(ws, message.data.sessionId);
          break;

        case 'unsubscribe_session':
          this.unsubscribeFromSession(ws, message.data.sessionId);
          break;

        case 'start_execution':
          if (ws.userId && message.data.sessionId) {
            await executionService.startExecution(message.data.sessionId, ws.userId);
          }
          break;

        case 'pause_execution':
          if (ws.userId && message.data.sessionId) {
            await executionService.pauseExecution(message.data.sessionId, ws.userId);
          }
          break;

        case 'cancel_execution':
          if (ws.userId && message.data.sessionId) {
            await executionService.cancelExecution(message.data.sessionId, ws.userId);
          }
          break;

        case 'user_input':
          if (message.data.sessionId && ws.userId) {
            const sent = this.sendToRuntime(ws.userId, {
              type: 'user_input',
              session_id: message.data.sessionId,
              input: message.data.input,
            });
            if (!sent) {
              // Fallback: try direct HTTP for local dev
              try {
                const inputUrl = new URL(`/input/${message.data.sessionId}`, config.agentRuntime.url);
                const inputBody = JSON.stringify({ input: message.data.input });
                const inputHost = (inputUrl.hostname === 'localhost' || inputUrl.hostname === '::1')
                  ? '127.0.0.1' : inputUrl.hostname;
                const inputReq = http.request({
                  hostname: inputHost,
                  port: parseInt(inputUrl.port || '80', 10),
                  path: inputUrl.pathname,
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                    'X-Runtime-Secret': config.agentRuntime.secret,
                    'Content-Length': String(Buffer.byteLength(inputBody)),
                  },
                  timeout: 5000,
                });
                inputReq.on('error', () => {});
                inputReq.write(inputBody);
                inputReq.end();
              } catch {}
            }
          }
          break;

        default:
          ws.send(JSON.stringify({
            event: 'error',
            data: { message: `Unknown event: ${message.event}` },
            timestamp: new Date().toISOString(),
          }));
      }
    } catch (error: any) {
      ws.send(JSON.stringify({
        event: 'error',
        data: { message: error.message },
        timestamp: new Date().toISOString(),
      }));
    }
  }

  private async subscribeToSession(ws: AuthenticatedSocket, sessionId: string) {
    // Verify session ownership before allowing subscription
    try {
      const prismaDB = (await import('../models')).default;
      const session = await prismaDB.executionSession.findUnique({
        where: { id: sessionId },
        select: { userId: true },
      });
      if (!session || session.userId !== ws.userId) {
        ws.send(JSON.stringify({
          event: 'error',
          data: { message: 'Forbidden: not your session' },
          timestamp: new Date().toISOString(),
        }));
        return;
      }
    } catch {
      // If check fails, deny access
      ws.send(JSON.stringify({
        event: 'error',
        data: { message: 'Session verification failed' },
        timestamp: new Date().toISOString(),
      }));
      return;
    }

    ws.sessionId = sessionId;
    if (!this.clients.has(sessionId)) {
      this.clients.set(sessionId, new Set());
    }
    this.clients.get(sessionId)!.add(ws);

    ws.send(JSON.stringify({
      event: 'subscribed',
      data: { sessionId },
      timestamp: new Date().toISOString(),
    }));

    logger.debug(`Client subscribed to session: ${sessionId}`);
  }

  private unsubscribeFromSession(ws: AuthenticatedSocket, sessionId: string) {
    const sessionClients = this.clients.get(sessionId);
    if (sessionClients) {
      sessionClients.delete(ws);
      if (sessionClients.size === 0) {
        this.clients.delete(sessionId);
      }
    }
    ws.sessionId = undefined;
  }

  private removeClient(ws: AuthenticatedSocket) {
    if (ws.sessionId) {
      this.unsubscribeFromSession(ws, ws.sessionId);
    }
  }

  // Send event to all clients subscribed to a session
  broadcastToSession(sessionId: string, event: string, data: any) {
    const sessionClients = this.clients.get(sessionId);
    if (!sessionClients) return;

    const message = JSON.stringify({
      event,
      data,
      timestamp: new Date().toISOString(),
    });

    sessionClients.forEach((client) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(message);
      }
    });
  }

  // Send event to a specific user. Returns number of clients that received the message.
  sendToUser(userId: string, event: string, data: any): number {
    const message = JSON.stringify({
      event,
      data,
      timestamp: new Date().toISOString(),
    });

    let sent = 0;
    this.wss.clients.forEach((client: WebSocket) => {
      const socket = client as AuthenticatedSocket;
      if (socket.userId === userId && socket.readyState === WebSocket.OPEN) {
        socket.send(message);
        sent++;
      }
    });
    return sent;
  }

  // ── Social System Broadcasting ──────────────────────────

  /**
   * Broadcast a new chat message to all owners of agents in the chat room.
   * Enables real-time spectating of agent conversations.
   */
  broadcastChatMessage(ownerUserIds: string[], message: any) {
    for (const userId of ownerUserIds) {
      this.sendToUser(userId, 'social:chat_message', message);
    }
  }

  /**
   * Broadcast a social notification (follow, friend, etc.) to the agent's owner.
   */
  broadcastSocialNotification(ownerUserId: string, notification: any) {
    this.sendToUser(ownerUserId, 'social:notification', notification);
  }

  /**
   * Broadcast follow/friend status change to the owner.
   */
  broadcastFollowUpdate(ownerUserId: string, data: { type: string; followerName: string; targetName: string; isMutual: boolean }) {
    this.sendToUser(ownerUserId, 'social:follow_update', data);
  }

  getConnectedCount(): number {
    return this.wss.clients.size;
  }
}

export let wsService: WebSocketService;

export function initWebSocket(server: HttpServer): WebSocketService {
  wsService = new WebSocketService(server);
  return wsService;
}
