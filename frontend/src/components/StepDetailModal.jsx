import { useState } from 'react';
import { renderMarkdown } from './ResultDisplay';
import { FileText, Terminal, Box, Clock } from 'lucide-react';

export function StepDetailModal({ step, logs, artifacts, onClose }) {
    const [activeTab, setActiveTab] = useState('output');

    if (!step) return null;

    const statusColors = {
        pending: '#94a3b8',
        in_progress: '#3b82f6',
        completed: '#10b981',
        failed: '#ef4444',
        retrying: '#f59e0b',
    };

    const statusColor = statusColors[step.status] || statusColors.pending;

    // Filter logs and artifacts for this step
    // Note: step.id might be numeric in plan but string in logs, so looser comparison
    const stepLogs = logs?.filter(l => l.step_id && String(l.step_id) === String(step.id)) || [];
    const stepArtifacts = artifacts?.filter(a => a.step_id && String(a.step_id) === String(step.id)) || [];

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal glass-panel" onClick={e => e.stopPropagation()} style={{ maxWidth: '900px', width: '90%', height: '80vh', display: 'flex', flexDirection: 'column', padding: 0 }}>
                {/* Header */}
                <div style={{
                    padding: '20px',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    background: 'rgba(0,0,0,0.2)'
                }}>
                    <div style={{
                        width: '40px',
                        height: '40px',
                        background: `${statusColor}20`,
                        borderRadius: '10px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '1.25rem',
                        border: `1px solid ${statusColor}40`
                    }}>
                        {step.agent_icon || <Box size={20} color={statusColor} />}
                    </div>
                    <div style={{ flex: 1 }}>
                        <h3 style={{ margin: 0, fontSize: '1.1rem', color: '#efefef' }}>Step {step.label || 'Details'}</h3>
                        <div style={{ fontSize: '0.875rem', color: '#9ca3af', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ textTransform: 'uppercase', fontWeight: 600, fontSize: '0.75rem' }}>{step.agent_type}</span>
                            <span>•</span>
                            <span style={{ color: statusColor, textTransform: 'capitalize', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                {step.status?.replace('_', ' ')}
                            </span>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            background: 'none',
                            border: 'none',
                            fontSize: '1.5rem',
                            color: '#6b7280',
                            cursor: 'pointer',
                            padding: '8px',
                            lineHeight: 1
                        }}
                    >
                        ×
                    </button>
                </div>

                {/* Tabs */}
                <div style={{
                    display: 'flex',
                    gap: '2px',
                    padding: '0 20px',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                    background: 'rgba(0,0,0,0.1)'
                }}>
                    {['output', 'logs', 'artifacts'].map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            style={{
                                padding: '12px 16px',
                                background: 'none',
                                border: 'none',
                                borderBottom: activeTab === tab ? `2px solid ${statusColor}` : '2px solid transparent',
                                color: activeTab === tab ? '#efefef' : '#6b7280',
                                cursor: 'pointer',
                                textTransform: 'capitalize',
                                fontWeight: activeTab === tab ? 600 : 400,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                transition: 'all 0.2s'
                            }}
                        >
                            {tab === 'output' && <FileText size={14} />}
                            {tab === 'logs' && <Terminal size={14} />}
                            {tab === 'artifacts' && <Box size={14} />}
                            {tab}
                            {tab === 'logs' && stepLogs.length > 0 && (
                                <span style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem' }}>{stepLogs.length}</span>
                            )}
                            {tab === 'artifacts' && stepArtifacts.length > 0 && (
                                <span style={{ background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.7rem' }}>{stepArtifacts.length}</span>
                            )}
                        </button>
                    ))}
                </div>

                {/* Body */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>

                    {/* Description Alert */}
                    <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                        <h4 style={{ margin: '0 0 8px 0', fontSize: '0.75rem', color: '#6b7280', textTransform: 'uppercase' }}>Goal</h4>
                        <p style={{ margin: 0, color: '#e5e7eb', lineHeight: 1.5 }}>{step.description}</p>
                    </div>

                    {step.error && (
                        <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                            <h4 style={{ margin: '0 0 8px 0', fontSize: '0.75rem', color: '#ef4444', textTransform: 'uppercase' }}>Error</h4>
                            <p style={{ margin: 0, color: '#fca5a5' }}>{step.error}</p>
                        </div>
                    )}

                    {activeTab === 'output' && (
                        <div className="result-markdown fade-in">
                            {step.result ? (
                                renderMarkdown(step.result)
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', color: '#6b7280', gap: '12px' }}>
                                    <FileText size={40} strokeWidth={1} style={{ opacity: 0.5 }} />
                                    <span>{step.status === 'in_progress' ? 'Generating output...' : 'No output produced yet.'}</span>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'logs' && (
                        <div className="fade-in" style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>
                            {stepLogs.length > 0 ? (
                                stepLogs.map((log, idx) => (
                                    <div key={idx} style={{
                                        padding: '8px 12px',
                                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                                        display: 'flex',
                                        gap: '12px',
                                        color: log.level === 'error' ? '#ef4444' : log.level === 'warning' ? '#f59e0b' : '#94a3b8'
                                    }}>
                                        <span style={{ color: '#525252', whiteSpace: 'nowrap', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <Clock size={10} />
                                            {new Date(log.timestamp).toLocaleTimeString([], { hour12: false })}
                                        </span>
                                        <span style={{ flex: 1 }}>{log.message}</span>
                                    </div>
                                ))
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', color: '#6b7280', gap: '12px' }}>
                                    <Terminal size={40} strokeWidth={1} style={{ opacity: 0.5 }} />
                                    <span>No activity logs for this step.</span>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'artifacts' && (
                        <div className="grid-responsive fade-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '16px' }}>
                            {stepArtifacts.length > 0 ? (
                                stepArtifacts.map(artifact => (
                                    <div key={artifact.id} style={{
                                        background: 'rgba(255,255,255,0.03)',
                                        border: '1px solid rgba(255,255,255,0.05)',
                                        borderRadius: '8px',
                                        padding: '16px',
                                        cursor: 'pointer',
                                        transition: 'all 0.2s',
                                        display: 'flex',
                                        flexDirection: 'column',
                                        gap: '12px'
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#efefef', fontWeight: 500 }}>
                                            <Box size={16} color="#3b82f6" />
                                            {artifact.name}
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: '#6b7280', textTransform: 'uppercase' }}>
                                            {artifact.type}
                                        </div>
                                        {/* Preview logic could go here */}
                                        <div style={{ fontSize: '0.85rem', color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
                                            {typeof artifact.content === 'string' ? artifact.content : JSON.stringify(artifact.content)}
                                        </div>
                                    </div>
                                ))
                            ) : (
                                <div style={{ gridColumn: '1 / -1', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', color: '#6b7280', gap: '12px' }}>
                                    <Box size={40} strokeWidth={1} style={{ opacity: 0.5 }} />
                                    <span>No artifacts produced by this step.</span>
                                </div>
                            )}
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}
