function formatTime(timestamp) {
    if (!timestamp) return '';
    try {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    } catch {
        return '';
    }
}

const AGENT_ICONS = {
    orchestrator: '🎯',
    researcher: '🔍',
    coder: '💻',
    analyst: '📊',
    writer: '✍️',
};

export function LogsPanel({ logs }) {
    if (!logs || logs.length === 0) {
        return (
            <div className="agent-panel">
                <div className="panel-header">
                    📜 Activity Log
                </div>
                <div className="panel-content">
                    <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                        <p style={{ fontSize: '0.875rem' }}>No activity yet</p>
                    </div>
                </div>
            </div>
        );
    }

    // Show last 15 logs, reversed (newest first)
    const recentLogs = [...logs].slice(-15).reverse();

    return (
        <div className="agent-panel">
            <div className="panel-header">
                📜 Activity Log ({logs.length} events)
            </div>
            <div className="panel-content logs-panel">
                {recentLogs.map((log, index) => (
                    <div
                        key={index}
                        className={`log-entry ${log.level || 'info'}`}
                    >
                        <span className="log-time">
                            {formatTime(log.timestamp)}
                        </span>
                        <span className="log-agent">
                            {AGENT_ICONS[log.agent_type] || '🤖'}
                        </span>
                        <span className="log-message">
                            {log.message}
                        </span>
                    </div>
                ))}
            </div>
        </div>
    );
}
