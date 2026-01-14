class WebSocketManager {
  constructor() {
    this.ws = null;
    this.listeners = {};
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectInterval = 3000;
    this.connectionState = 'disconnected'; // 添加连接状态跟踪
  }

  // 连接到WebSocket服务器
  connect(url = `ws://${window.location.hostname}:8000/api/ws`) {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emit('websocket_max_reconnect_reached');
      console.log('达到最大重连次数，停止重连');
      return
    }
    console.log(`[WebSocket] 尝试连接到: ${url}`);
    
    // 如果已经有连接，先关闭
    if (this.ws) {
      console.log('[WebSocket] 关闭现有连接');
      this.ws.close();
    }

    try {
      this.connectionState = 'connecting';
      this.ws = new WebSocket(url);
      
      this.ws.onopen = () => {
        console.log('[WebSocket] ✅ 连接成功建立');
        this.connectionState = 'connected';
        this.reconnectAttempts = 0;
        
        // 触发连接成功事件
        this.emit('websocket_connected', { url, timestamp: new Date().toISOString() });
      };
      
      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.emit(message.type, message.data || message);
        } catch (error) {
          console.error('[WebSocket] ❌ 消息解析失败:', error, '原始数据:', event.data);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log(`[WebSocket] 🔌 连接关闭 - 代码: ${event.code}, 原因: ${event.reason}, 是否正常: ${event.wasClean}`);
        this.connectionState = 'disconnected';
        
        // 触发连接关闭事件
        this.emit('websocket_disconnected', { 
          code: event.code, 
          reason: event.reason, 
          wasClean: event.wasClean,
          timestamp: new Date().toISOString()
        });
        
        // 只有在非正常关闭时才尝试重连
        if (!event.wasClean) {
          this.attemptReconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        console.error('[WebSocket] ❌ 连接错误:', error);
        this.connectionState = 'error';
        
        // 触发错误事件
        this.emit('websocket_error', { 
          error: error.message || 'WebSocket连接错误', 
          timestamp: new Date().toISOString()
        });
      };
      
      // 设置连接超时检测
      setTimeout(() => {
        if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
          console.warn('[WebSocket] ⚠️ 连接超时，可能后端服务未启动');
          this.ws.close();
        }
      }, 5000);
      
    } catch (error) {
      console.error('[WebSocket] ❌ 创建连接失败:', error);
      this.connectionState = 'error';
      this.emit('websocket_error', { 
        error: error.message || 'WebSocket创建失败', 
        timestamp: new Date().toISOString()
      });
    }
  }

  disconnect() {
    console.log('[WebSocket] 🔌 主动断开连接');
    if (this.ws) {
      this.ws.close(1000, '用户主动断开'); // 正常关闭
      this.ws = null;
    }
    this.connectionState = 'disconnected';
  }

  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`[WebSocket] 🔄 尝试重连... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
      
      setTimeout(() => {
        if (this.connectionState !== 'connected') {
          this.connect();
        }
      }, this.reconnectInterval);
    } else {
      console.error('[WebSocket] ❌ 重连次数已达上限，停止重连');
      this.emit('websocket_max_reconnect_reached', {
        attempts: this.reconnectAttempts,
        timestamp: new Date().toISOString()
      });
    }
  }

  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
    console.log(`[WebSocket] 📝 注册事件监听器: ${event}`);
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
      console.log(`[WebSocket] 🗑️ 移除事件监听器: ${event}`);
    }
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error(`[WebSocket] ❌ 事件监听器错误 (${event}):`, error);
        }
      });
    } else {
      console.warn(`[WebSocket] ⚠️ 没有找到事件监听器: ${event}`);
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const jsonData = JSON.stringify(data);
      this.ws.send(jsonData);
      return true;
    } else {
      console.warn('[WebSocket] ⚠️ 无法发送消息，连接状态:', this.getReadyStateText());
      return false;
    }
  }

  getReadyStateText() {
    if (!this.ws) return 'null';
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING: return 'CONNECTING';
      case WebSocket.OPEN: return 'OPEN';
      case WebSocket.CLOSING: return 'CLOSING';
      case WebSocket.CLOSED: return 'CLOSED';
      default: return 'UNKNOWN';
    }
  }

  getStatus() {
    return {
      connectionState: this.connectionState,
      readyState: this.ws ? this.getReadyStateText() : 'null',
      reconnectAttempts: this.reconnectAttempts,
      maxReconnectAttempts: this.maxReconnectAttempts,
      hasWebSocket: !!this.ws
    };
  }
}

export default WebSocketManager;