import { useEffect, useState } from 'react';
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

export function AgentStatusPanel({ plan, currentStep, logs, toolActivity }) {
    const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES);
    const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES);
    const [agentsList, setAgentsList] = useState([]);

    // Poll for agents list (independent of plan updates)
    useEffect(() => {
        const fetchAgents = async () => {
            try {
                const res = await fetch('/api/agents');
                const data = await res.json();
                setAgentsList(data);
            } catch (e) {
                console.error("Failed to fetch agents:", e);
            }
        };

        fetchAgents();
        const interval = setInterval(fetchAgents, 5000);
        return () => clearInterval(interval);
    }, []);

    const handleDeleteAgent = async (agentId) => {
        if (!agentId) return;
        try {
            const res = await fetch(`/api/agents/${agentId}`, { method: 'DELETE' });
            if (res.ok) {
                // Refresh list immediately
                const resList = await fetch('/api/agents');
                const data = await resList.json();
                setAgentsList(data);
            } else {
                console.error("Failed to delete agent");
            }
        } catch (e) {
            console.error("Error deleting agent:", e);
        }
    };

    // Rebuild nodes when agentsList or plan/status changes
    useEffect(() => {
        if (agentsList.length === 0) return;

        // Merge with existing config or create new positions
        let newNodes = [];

        // Always add Orchestrator first
        const orch = agentsList.find(a => a.id === 'orchestrator');
        if (orch) {
            newNodes.push({
                id: 'orchestrator',
                type: 'agentNode',
                position: AGENT_CONFIG.orchestrator.position,
                data: {
                    label: 'Orchestrator',
                    status: getAgentStatus('orchestrator', plan),
                    agent_type: 'orchestrator',
                    description: 'Idle',
                    isCustom: false
                }
            });
        }

        // Process other agents
        const otherAgents = agentsList.filter(a => a.id !== 'orchestrator');
        otherAgents.forEach((agent, index) => {
            let position;
            if (AGENT_CONFIG[agent.id]) {
                position = AGENT_CONFIG[agent.id].position;
            } else {
                position = { x: (index % 5) * 300, y: 250 + (Math.floor(index / 5) * 150) };
            }

            const lastLog = logs?.filter(l => l.agent_type === agent.id).pop();
            const activeTool = toolActivity && toolActivity.agent === agent.id ? toolActivity : null;
            const status = getAgentStatus(agent.id, plan);

            let description = 'Idle';
            if (activeTool) {
                description = activeTool.tool === 'web_search_api'
                    ? `🔎 "${activeTool.query}"`
                    : `🔧 Using ${activeTool.tool}`;
            } else if (lastLog) {
                description = lastLog.message;
            } else if (status === 'in_progress') {
                description = 'Working...';
            }

            newNodes.push({
                id: agent.id,
                type: 'agentNode',
                position,
                data: {
                    label: agent.name,
                    status: status,
                    agent_type: agent.id,
                    description: description,
                    isCustom: agent.type === 'custom',
                    onDelete: handleDeleteAgent
                }
            });
        });

        // Use functional state update to preserve user-dragged positions
        setNodes((prevNodes) => {
            const prevNodeMap = new Map(prevNodes.map(n => [n.id, n]));
            return newNodes.map(n => {
                const prev = prevNodeMap.get(n.id);
                if (prev) {
                    // Keep the user's current position, only update data/style
                    return {
                        ...n,
                        position: prev.position,
                        positionAbsolute: prev.positionAbsolute
                    };
                }
                return n;
            });
        });

        // Update edges
        const newEdges = newNodes
            .filter(n => n.id !== 'orchestrator')
            .map(node => {
                const status = getAgentStatus(node.id, plan);
                const isCompleted = status === 'completed';
                const activeColor = '#3b82f6';
                const completedColor = '#10b981';
                const edgeColor = isCompleted ? completedColor : activeColor;

                return {
                    id: `orchestrator-${node.id}`,
                    source: 'orchestrator',
                    target: node.id,
                    type: 'animated',
                    animated: true,
                    data: {
                        isActive: true,
                        isCompleted
                    },
                    style: {
                        stroke: edgeColor,
                        strokeWidth: 3,
                        filter: `drop-shadow(0 0 4px ${edgeColor})`,
                        opacity: 1
                    },
                    markerEnd: {
                        type: MarkerType.ArrowClosed,
                        color: edgeColor,
                    },
                };
            });
        setEdges(newEdges);

    }, [agentsList, plan, logs, toolActivity, setNodes, setEdges]);

    return (
        <div className="agent-panel agent-panel-container" style={{ background: '#0a0a0a', borderRadius: '12px', border: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
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
