import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Custom hook for WebSocket connection to the backend.
 * Handles connection, reconnection, and message handling.
 */
export function useWebSocket(sessionId = null, onMessage = null) {
    const [isConnected, setIsConnected] = useState(false);
    const [lastMessage, setLastMessage] = useState(null);
    const [messages, setMessages] = useState([]);
    const wsRef = useRef(null);
    const reconnectTimeoutRef = useRef(null);
    const onMessageRef = useRef(onMessage);
    const intentionalDisconnectRef = useRef(false);

    // Update ref when callback changes
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    const connect = useCallback(() => {
        intentionalDisconnectRef.current = false;
        // Determine WebSocket URL
        const apiUrl = import.meta.env.VITE_API_URL || '';
        const isSecure = apiUrl.startsWith('https:');
        const defaultProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const defaultHost = window.location.host;

        let wsUrl;
        if (apiUrl) {
            const wsBase = apiUrl.replace(/^http/, 'ws').replace(/\/$/, '');
            wsUrl = sessionId ? `${wsBase}/ws/${sessionId}` : `${wsBase}/ws`;
        } else {
            wsUrl = sessionId
                ? `${defaultProtocol}//${defaultHost}/ws/${sessionId}`
                : `${defaultProtocol}//${defaultHost}/ws`;
        }

        try {
            const ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('WebSocket connected');
                setIsConnected(true);

                // Clear any pending reconnect
                if (reconnectTimeoutRef.current) {
                    clearTimeout(reconnectTimeoutRef.current);
                    reconnectTimeoutRef.current = null;
                }
            };

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    setLastMessage(data);
                    setMessages(prev => [...prev.slice(-499), data]);

                    // Call callback if provided
                    if (onMessageRef.current) {
                        onMessageRef.current(data);
                    }
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected');
                setIsConnected(false);
                wsRef.current = null;

                // Only reconnect if not intentionally disconnected
                if (!intentionalDisconnectRef.current) {
                    reconnectTimeoutRef.current = setTimeout(() => {
                        console.log('Attempting to reconnect...');
                        connect();
                    }, 3000);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                setIsConnected(false);
            };

            wsRef.current = ws;
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
        }
    }, [sessionId]);

    const disconnect = useCallback(() => {
        intentionalDisconnectRef.current = true;
        if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
            reconnectTimeoutRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
    }, []);

    const sendMessage = useCallback((message) => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(message));
        }
    }, []);

    const subscribe = useCallback((newSessionId) => {
        sendMessage({ type: 'subscribe', session_id: newSessionId });
    }, [sendMessage]);

    const clearMessages = useCallback(() => {
        setMessages([]);
        setLastMessage(null);
    }, []);

    // Connect on mount
    useEffect(() => {
        connect();
        return () => disconnect();
    }, [connect, disconnect]);

    // Keepalive ping
    useEffect(() => {
        const interval = setInterval(() => {
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                sendMessage({ type: 'ping' });
            }
        }, 25000);

        return () => clearInterval(interval);
    }, [sendMessage]);

    return {
        isConnected,
        lastMessage,
        messages,
        sendMessage,
        subscribe,
        clearMessages,
        connect,
        disconnect,
    };
}
