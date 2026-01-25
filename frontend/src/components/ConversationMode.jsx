import { useState } from 'react';

export function ConversationMode({
    sessionId,
    isActive,
    status,
    conversationHistory,
    onSendMessage,
    onRefine
}) {
    const [message, setMessage] = useState('');

    const isCompleted = status === 'completed';
    // Always allow chat if session is active
    const canChat = isActive;

    const handleSend = () => {
        if (!message.trim()) return;
        onSendMessage(message.trim());
        setMessage('');
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="agent-panel">
            <div className="panel-header">
                💬 Live Conversation
                {isCompleted && (
                    <span style={{
                        marginLeft: 'auto',
                        fontSize: '0.75rem',
                        background: '#10b981',
                        color: 'white',
                        padding: '2px 8px',
                        borderRadius: '12px'
                    }}>
                        Refinement Active
                    </span>
                )}
            </div>
            <div className="panel-content">
                {/* Conversation History */}
                <div className="conversation-history" style={{
                    maxHeight: '200px',
                    overflowY: 'auto',
                    marginBottom: '0.75rem'
                }}>
                    {conversationHistory && conversationHistory.length > 0 ? (
                        conversationHistory.map((entry, index) => (
                            <div
                                key={index}
                                className={`chat-message ${entry.role}`}
                                style={{
                                    padding: '0.5rem',
                                    marginBottom: '0.5rem',
                                    borderRadius: 'var(--radius-md)',
                                    background: entry.role === 'user'
                                        ? 'rgba(99, 102, 241, 0.1)'
                                        : 'var(--color-bg-card)',
                                    fontSize: '0.875rem'
                                }}
                            >
                                <div style={{
                                    fontSize: '0.7rem',
                                    color: 'var(--color-text-muted)',
                                    marginBottom: '0.25rem'
                                }}>
                                    {entry.role === 'user' ? '👤 You' : '🤖 Orchestrator'}
                                    {entry.type === 'refinement' && ' (Refinement)'}
                                </div>
                                <div style={{ color: 'var(--color-text-secondary)' }}>
                                    {entry.content?.replace('[Refinement]: ', '')}
                                </div>
                            </div>
                        ))
                    ) : (
                        <div style={{
                            textAlign: 'center',
                            color: 'var(--color-text-muted)',
                            fontSize: '0.875rem',
                            padding: '1rem'
                        }}>
                            Start a request to enable conversation.
                            You can ask questions or request refinements at any time.
                        </div>
                    )}
                </div>

                {/* Input Area */}
                {isActive && (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                            type="text"
                            className="request-input"
                            style={{
                                minHeight: 'auto',
                                padding: '0.5rem 0.75rem',
                                flex: 1
                            }}
                            placeholder={isCompleted
                                ? 'Ask a question or request changes...'
                                : 'Type a message...'}
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            onKeyPress={handleKeyPress}
                        />
                        <button
                            className="btn btn-primary"
                            style={{ padding: '0.5rem 1rem' }}
                            onClick={handleSend}
                            disabled={!message.trim()}
                        >
                            📤
                        </button>
                    </div>
                )}

                {isCompleted && (
                    <div style={{
                        fontSize: '0.7rem',
                        color: 'var(--color-text-muted)',
                        marginTop: '0.5rem'
                    }}>
                        💡 Tip: You can ask to "refine the results", "add more info", or "change the style".
                    </div>
                )}
            </div>
        </div>
    );
}
