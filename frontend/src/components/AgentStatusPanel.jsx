import { useEffect } from 'react';
import ReactFlow, {
    Background,
    useNodesState,
    useEdgesState,
    MarkerType,
    Controls,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { nodeTypes } from './FlowNodes';
import { edgeTypes } from './AnimatedEdge';
import { BrainCircuit } from 'lucide-react';

const AGENT_CONFIG = {
    orchestrator: { label: 'Orchestrator', color: '#6366f1', position: { x: 450, y: 0 } },
    researcher: { label: 'Researcher', color: '#3b82f6', position: { x: 0, y: 250 } },
    analyst: { label: 'Analyst', color: '#8b5cf6', position: { x: 300, y: 250 } },
    coder: { label: 'Coder', color: '#10b981', position: { x: 600, y: 250 } },
    writer: { label: 'Writer', color: '#f59e0b', position: { x: 900, y: 250 } },
};

const INITIAL_NODES = Object.entries(AGENT_CONFIG).map(([type, config]) => ({
    id: type,
    type: 'agentNode',
    position: config.position,
    data: {
        label: config.label,
        status: 'pending',
        agent_type: type,
        description: 'Idle'
    }
}));

const INITIAL_EDGES = Object.keys(AGENT_CONFIG)
    .filter(type => type !== 'orchestrator')
    .map(type => ({
        id: `orchestrator-${type}`,
        source: 'orchestrator',
        target: type,
        type: 'animated',
        animated: false,
        style: { stroke: '#333', strokeWidth: 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#333' },
        data: { isActive: false, isCompleted: false },
    }));

function getAgentStatus(agentType, plan) {
    if (agentType === 'orchestrator') {
        if (!plan || plan.length === 0) return 'pending';
        const allCompleted = plan.every(s => s.status === 'completed');
        return allCompleted ? 'completed' : 'in_progress';
    }

    if (!plan || plan.length === 0) return 'pending';

    const agentSteps = plan.filter(s => s.agent_type === agentType);
    if (agentSteps.length === 0) return 'pending';

    const hasActive = agentSteps.some(s => s.status === 'in_progress');
    const hasFailed = agentSteps.some(s => s.status === 'failed');
    const hasCompleted = agentSteps.some(s => s.status === 'completed');

    if (hasActive) return 'in_progress';
    if (hasFailed) return 'failed';
    if (hasCompleted) return 'completed';
    return 'pending';
}

export function AgentStatusPanel({ plan, currentStep, logs }) {
    const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES);
    const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES);

    // Update node data when plan/logs change, without resetting position
    useEffect(() => {
        setNodes((nds) =>
            nds.map((node) => {
                const status = getAgentStatus(node.id, plan);
                const lastLog = logs?.filter(l => l.agent_type === node.id).pop();

                return {
                    ...node,
                    data: {
                        ...node.data,
                        status: status,
                        description: lastLog ? lastLog.message : (status === 'in_progress' ? 'Working...' : 'Idle')
                    }
                };
            })
        );
    }, [plan, logs, setNodes]);

    // Update edges based on status
    useEffect(() => {
        setEdges((eds) =>
            eds.map((edge) => {
                const targetId = edge.target;
                const status = getAgentStatus(targetId, plan);
                const isActive = status === 'in_progress';
                const isCompleted = status === 'completed';

                // Blue for active, Green for completed
                // User Request: Lines should ALWAYS be glowing and animated
                // We keep the color logic (Blue for active/pending, Green for completed) 
                // but force animation and glow effects.

                const activeColor = '#3b82f6';
                const completedColor = '#10b981';
                const inactiveColor = '#333';

                // Determine color based on status, but default to active blue if pending/idle
                // to ensure it looks "glowing" as requested.
                let edgeColor = activeColor;
                if (isCompleted) edgeColor = completedColor;

                return {
                    ...edge,
                    type: 'animated',
                    animated: true, // ALWAYS ANIMATED
                    data: {
                        isActive: true, // ALWAYS GLOWING
                        isCompleted
                    },
                    style: {
                        stroke: edgeColor,
                        strokeWidth: 3, // Always thick
                        filter: `drop-shadow(0 0 4px ${edgeColor})`, // Always glowing
                        opacity: 1
                    },
                    markerEnd: {
                        type: MarkerType.ArrowClosed,
                        color: edgeColor,
                    },
                };
            })
        );
    }, [plan, setEdges]);

    return (
        <div className="agent-panel" style={{ height: '400px', background: '#0a0a0a', borderRadius: '12px', border: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
            <div style={{
                padding: '16px',
                borderBottom: '1px solid #222',
                background: '#111',
                borderTopLeftRadius: '12px',
                borderTopRightRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                <BrainCircuit size={20} color="#6366f1" />
                <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#efefef', margin: 0 }}>Agent Network</h2>
            </div>

            <div style={{ flex: 1 }}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    nodeTypes={nodeTypes}
                    edgeTypes={edgeTypes}
                    fitView
                    proOptions={{ hideAttribution: true }}
                >
                    <Background color="#333" gap={16} />
                    <Controls />
                </ReactFlow>
            </div>
        </div>
    );
}
