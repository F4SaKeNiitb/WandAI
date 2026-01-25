import { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { motion } from 'framer-motion';

const nodeStyles = {
    padding: '10px 15px',
    borderRadius: '12px',
    background: '#1a1a1a',
    border: '1px solid #333',
    minWidth: '200px',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2)',
    transition: 'all 0.2s ease',
};

const statusColors = {
    pending: '#94a3b8',
    in_progress: '#3b82f6',
    completed: '#10b981',
    failed: '#ef4444',
    retrying: '#f59e0b',
};

const agentIcons = {
    researcher: '🔍',
    coder: '💻',
    analyst: '📊',
    writer: '📝',
    orchestrator: '🪄',
    default: '🤖'
};

const AgentNode = ({ data, selected }) => {
    const statusColor = statusColors[data.status] || statusColors.pending;
    const isActive = data.status === 'in_progress';
    const isError = data.status === 'failed';

    return (
        <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.3 }}
            style={{
                ...nodeStyles,
                borderColor: selected ? '#3b82f6' : isError ? '#ef4444' : isActive ? '#3b82f6' : '#333',
                boxShadow: isActive ? '0 0 0 2px rgba(59, 130, 246, 0.5)' : nodeStyles.boxShadow,
                display: 'flex',
                alignItems: 'center',
                gap: '12px'
            }}
        >
            <Handle type="target" position={Position.Top} style={{ width: '8px', height: '8px', background: '#9ca3af' }} />

            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '40px',
                    height: '40px',
                    borderRadius: '50%',
                    fontSize: '1.25rem',
                    background: `${statusColor}20`
                }}
            >
                {isActive ? (
                    <motion.div
                        animate={{ rotate: 360 }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                        style={{ display: 'flex' }}
                    >
                        {agentIcons[data.agent_type] || agentIcons.default}
                    </motion.div>
                ) : (
                    <span>{agentIcons[data.agent_type] || agentIcons.default}</span>
                )}
            </div>

            <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#efefef', margin: 0, lineHeight: 1.25 }}>
                    {data.label}
                </h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '4px' }}>
                    <span
                        style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: statusColor
                        }}
                    />
                    <span style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'capitalize' }}>
                        {data.status.replace('_', ' ')}
                    </span>
                </div>
            </div>

            {data.description && (
                <div style={{
                    marginTop: '8px',
                    fontSize: '0.75rem',
                    color: '#9ca3af',
                    borderTop: '1px solid #333',
                    paddingTop: '8px',
                    width: '100%'
                }}>
                    {data.description}
                </div>
            )}

            <Handle type="source" position={Position.Bottom} style={{ width: '8px', height: '8px', background: '#9ca3af' }} />
        </motion.div>
    );
};

export const nodeTypes = {
    agentNode: memo(AgentNode),
};
