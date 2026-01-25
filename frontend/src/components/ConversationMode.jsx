import { useState } from 'react';
import { Lightbulb } from 'lucide-react';

export function ConversationMode({
    sessionId,
    isActive,
    status,
    conversationHistory,
    onSendMessage,
    onRefine
}) {
    const [message, setMessage] = useState('');

    // Add style for typing animation
    const typingStyle = document.createElement('style');
    typingStyle.innerHTML = `
        @keyframes typing {
            0%, 100% { opacity: 0.3; transform: translateY(0); }
            50% { opacity: 1; transform: translateY(-2px); }
        }
        .typing-dot {
            width: 4px;
            height: 4px;
            background: #9ca3af;
            borderRadius: 50%;
            animation: typing 1.4s infinite;
        }
    `;
    if (!document.getElementById('typing-style')) {
        typingStyle.id = 'typing-style';
        document.head.appendChild(typingStyle);
    }

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
        <div className="agent-panel glass-panel">
            <div className="panel-header">
                Live Conversation
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
                                        : 'rgba(255, 255, 255, 0.05)',
                                    fontSize: '0.875rem'
                                }}
                            >
                                <div style={{
                                    fontSize: '0.7rem',
                                    color: 'var(--color-text-muted)',
                                    marginBottom: '0.25rem'
                                }}>
                                    {entry.role === 'user' ? 'You' : 'Orchestrator'}
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
                {/* Thinking Bubble */}
                {(status === 'planning' || status === 'executing') && (
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        marginBottom: '12px',
                        padding: '8px 12px',
                        borderRadius: '12px',
                        background: 'rgba(255, 255, 255, 0.05)',
                        width: 'fit-content',
                        marginLeft: '0'
                    }}>
                        <div className="typing-dot" style={{ animationDelay: '0s' }}></div>
                        <div className="typing-dot" style={{ animationDelay: '0.2s' }}></div>
                        <div className="typing-dot" style={{ animationDelay: '0.4s' }}></div>
                        <span style={{ fontSize: '0.75rem', color: '#9ca3af', marginLeft: '4px' }}>Thinking...</span>
                    </div>
                )}

                {/* Input Area */}
                {isActive && (
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <input
                            type="text"
                            className="request-input"
                            style={{
                                minHeight: 'auto',
                                padding: '0.5rem 0.75rem',
                                flex: 1,
                                background: 'rgba(0, 0, 0, 0.2)',
                                border: '1px solid rgba(255, 255, 255, 0.1)'
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
                            Send
                        </button>
                    </div>
                )}

                {isCompleted && (
                    <div style={{
                        fontSize: '0.7rem',
                        color: 'var(--color-text-muted)',
                        marginTop: '0.5rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px'
                    }}>
                        <Lightbulb size={12} /> Tip: You can ask to "refine the results", "add more info", or "change the style".
                    </div>
                )}
            </div>
        </div>
    );
}
