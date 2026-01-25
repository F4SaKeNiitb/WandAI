import { renderMarkdown } from './ResultDisplay';

export function StepDetailModal({ step, onClose }) {
    if (!step) return null;

    const statusColors = {
        pending: '#94a3b8',
        in_progress: '#3b82f6',
        completed: '#10b981',
        failed: '#ef4444',
        retrying: '#f59e0b',
    };

    const statusColor = statusColors[step.status] || statusColors.pending;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '800px', width: '90%' }}>
                <div className="modal-header" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <div style={{
                        width: '32px',
                        height: '32px',
                        background: `${statusColor}20`,
                        borderRadius: '50%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '1.25rem'
                    }}>
                        {step.agent_icon}
                    </div>
                    <div>
                        <h3 style={{ margin: 0 }}>{step.label}</h3>
                        <div style={{ fontSize: '0.875rem', color: '#6b7280', marginTop: '2px' }}>
                            {step.agent_type.toUpperCase()} • <span style={{ color: statusColor, textTransform: 'capitalize' }}>{step.status.replace('_', ' ')}</span>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            marginLeft: 'auto',
                            background: 'none',
                            border: 'none',
                            fontSize: '1.5rem',
                            color: '#6b7280',
                            cursor: 'pointer',
                            padding: '4px 8px'
                        }}
                    >
                        ×
                    </button>
                </div>

                <div className="modal-body" style={{ overflowY: 'auto', maxHeight: '70vh' }}>

                    <div style={{ marginBottom: '1.5rem' }}>
                        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Description</h4>
                        <p style={{ margin: 0, padding: '12px', background: '#1e293b', borderRadius: '8px', border: '1px solid #334155', color: '#f8fafc' }}>
                            {step.description}
                        </p>
                    </div>

                    {step.error && (
                        <div style={{ marginBottom: '1.5rem' }}>
                            <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: '#ef4444', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Error</h4>
                            <div style={{ padding: '12px', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fee2e2', color: '#b91c1c' }}>
                                {step.error}
                            </div>
                        </div>
                    )}

                    <div>
                        <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Output</h4>
                        <div className="result-markdown" style={{ padding: '16px', background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', color: '#f8fafc' }}>
                            {step.result ? (
                                renderMarkdown(step.result)
                            ) : (
                                <span style={{ color: '#9ca3af', fontStyle: 'italic' }}>
                                    {step.status === 'pending' || step.status === 'in_progress' ? 'Waiting for output...' : 'No output produced.'}
                                </span>
                            )}
                        </div>
                    </div>

                </div>

                <div className="modal-footer">
                    <button className="btn btn-primary" onClick={onClose}>
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
