import { useEffect, useMemo, useCallback, useState } from 'react';
import ReactFlow, {
    Background,
    Controls,
    useNodesState,
    useEdgesState,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';
import { nodeTypes } from './FlowNodes';
import { StepDetailModal } from './StepDetailModal';
import { CreateAgentModal } from './CreateAgentModal';
import dagre from 'dagre';
import { Edit2, Save, X, Loader2, CheckCircle2, XCircle, AlertTriangle, Search, Code2, LineChart, PenTool, BrainCircuit, Bot, Plus, Trash2 } from 'lucide-react';

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const getLayoutedElements = (nodes, edges) => {
    const nodeWidth = 250;
    const nodeHeight = 100;

    dagreGraph.setGraph({ rankdir: 'TB' });

    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        node.position = {
            x: nodeWithPosition.x - nodeWidth / 2,
            y: nodeWithPosition.y - nodeHeight / 2,
        };
        return node;
    });

    return { nodes: layoutedNodes, edges };
};

const AGENT_ICONS = {
    orchestrator: <BrainCircuit size={14} />,
    researcher: <Search size={14} />,
    coder: <Code2 size={14} />,
    analyst: <LineChart size={14} />,
    writer: <PenTool size={14} />,
};

export function PlanViewer({ plan, currentStep, onUpdatePlan, isEditable, logs, artifacts, apiBaseUrl }) {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesState] = useEdgesState([]);
    const [selectedStep, setSelectedStep] = useState(null);
    const [isEditing, setIsEditing] = useState(false);
    const [editedPlan, setEditedPlan] = useState([]);
    const [availableAgents, setAvailableAgents] = useState([]);
    const [showCreateAgentModal, setShowCreateAgentModal] = useState(false);

    // Fetch available agents on load
    useEffect(() => {
        const url = apiBaseUrl ? `${apiBaseUrl}/api/agents` : '/api/agents';
        fetch(url)
            .then(res => res.json())
            .then(data => setAvailableAgents(data))
            .catch(err => console.error("Failed to load agents:", err));
    }, [apiBaseUrl]);

    // Sync edited plan when entering edit mode, and ensure agents are loaded
    useEffect(() => {
        if (isEditing) {
            if (plan) {
                setEditedPlan(JSON.parse(JSON.stringify(plan)));
            }
            // Refetch agents to ensure we have the latest list (e.g. if new custom agent was just added)
            const url = apiBaseUrl ? `${apiBaseUrl}/api/agents` : '/api/agents';
            fetch(url)
                .then(res => res.json())
                .then(data => {
                    console.log("Loaded agents for editor:", data);
                    setAvailableAgents(data);
                })
                .catch(err => console.error("Failed to load agents:", err));
        }
    }, [isEditing, plan, apiBaseUrl]);

    const handlePlanChange = (index, field, value) => {
        const newPlan = [...editedPlan];
        newPlan[index][field] = value;
        setEditedPlan(newPlan);
    };

    const handleAddStep = (index) => {
        const newStep = {
            id: 'step-' + Math.random().toString(36).substr(2, 9),
            description: 'New Step',
            agent_type: 'researcher',
            status: 'pending',
            dependencies: []
        };
        const newPlan = [...editedPlan];
        newPlan.splice(index, 0, newStep);
        setEditedPlan(newPlan);
    };

    const handleDeleteStep = (index) => {
        if (editedPlan.length <= 1) return;
        const newPlan = [...editedPlan];
        newPlan.splice(index, 1);
        setEditedPlan(newPlan);
    };

    const handleSave = () => {
        // Merge edited fields with original plan, preserving statuses
        const mergedPlan = plan.map((originalStep, index) => {
            const editedStep = editedPlan[index];
            return {
                ...originalStep,
                description: editedStep.description,
                agent_type: editedStep.agent_type,
            };
        });
        onUpdatePlan(mergedPlan);
        setIsEditing(false);
    };

    const onNodeClick = useCallback((event, node) => {
        if (node.type === 'agentNode') {
            setSelectedStep(node.data);
        }
    }, []);

    // Transform plan into graph elements
    useEffect(() => {
        if (!plan || plan.length === 0) return;

        const newNodes = plan.map((step, index) => ({
            id: step.id,
            type: 'agentNode',
            data: {
                label: `Step ${index + 1}: ${step.agent_type}`,
                description: step.description,
                status: step.status || 'pending',
                agent_type: step.agent_type,
                result: step.result,
                error: step.error
            },
            position: { x: 0, y: 0 }, // Position handled by layout
        }));

        const newEdges = [];
        plan.forEach((step) => {
            if (step.dependencies && step.dependencies.length > 0) {
                step.dependencies.forEach((depId) => {
                    // Only add edge if dependency exists in plan
                    if (plan.find(p => p.id === depId)) {
                        const isCompleted = step.status === 'completed' || step.status === 'in_progress';
                        newEdges.push({
                            id: `${depId}-${step.id}`,
                            source: depId,
                            target: step.id,
                            animated: step.status === 'in_progress',
                            style: { stroke: isCompleted ? '#3b82f6' : '#94a3b8', strokeWidth: 2 },
                            markerEnd: {
                                type: MarkerType.ArrowClosed,
                                color: isCompleted ? '#3b82f6' : '#94a3b8',
                            },
                        });
                    }
                });
            } else if (newNodes.length > 0 && newNodes[0].id !== step.id) {
                // Determine implicit sequential edges if no explicit deps
                const stepIndex = plan.findIndex(p => p.id === step.id);
                if (stepIndex > 0) {
                    const prevStep = plan[stepIndex - 1];
                    const isCompleted = step.status === 'completed' || step.status === 'in_progress';
                    newEdges.push({
                        id: `${prevStep.id}-${step.id}`,
                        source: prevStep.id,
                        target: step.id,
                        animated: step.status === 'in_progress',
                        style: { stroke: isCompleted ? '#3b82f6' : '#94a3b8', strokeWidth: 2, strokeDasharray: '5,5' },
                        markerEnd: {
                            type: MarkerType.ArrowClosed,
                            color: isCompleted ? '#3b82f6' : '#94a3b8',
                        },
                    });
                }
            }
        });

        // Apply layout
        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
            newNodes,
            newEdges
        );

        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
    }, [plan, setNodes, setEdges]); // Rerun when plan updates

    return (
        <div className="plan-viewer glass-panel" style={{ height: '500px', borderRadius: '12px', overflow: 'hidden' }}>
            <div style={{
                padding: '16px',
                borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                background: 'rgba(0, 0, 0, 0.2)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <h2 style={{ fontSize: '1.125rem', fontWeight: 600, color: '#efefef', margin: 0 }}>Execution Plan</h2>
                    {isEditable && !isEditing && (
                        <button
                            className="btn-xs"
                            onClick={() => setIsEditing(true)}
                            style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: 'rgba(255, 255, 255, 0.1)',
                                color: '#efefef',
                                borderRadius: '4px',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                                transition: 'all 0.2s'
                            }}
                            onMouseEnter={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.2)'}
                            onMouseLeave={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.1)'}
                        >
                            <Edit2 size={12} /> Edit
                        </button>
                    )}
                    {isEditing && (
                        <div style={{ display: 'flex', gap: '4px' }}>
                            <button
                                onClick={handleSave}
                                style={{
                                    padding: '4px 8px',
                                    fontSize: '0.75rem',
                                    background: '#22c55e',
                                    color: 'white',
                                    borderRadius: '4px',
                                    border: 'none',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px'
                                }}
                            >
                                <Save size={12} /> Save
                            </button>
                            <button
                                onClick={() => setIsEditing(false)}
                                style={{
                                    padding: '4px 8px',
                                    fontSize: '0.75rem',
                                    background: '#ef4444',
                                    color: 'white',
                                    borderRadius: '4px',
                                    border: 'none',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px'
                                }}
                            >
                                <X size={12} /> Cancel
                            </button>
                        </div>
                    )}
                </div>
                <div style={{ fontSize: '0.875rem', color: '#9ca3af' }}>
                    {plan.length} steps • Step {currentStep + 1} active
                </div>
            </div>

            <div style={{ height: 'calc(100% - 60px)', overflowY: isEditing ? 'auto' : 'hidden' }}>
                {isEditing ? (
                    <div className="plan-editor" style={{ padding: '16px' }}>
                        {editedPlan.map((step, index) => {
                            const originalStep = plan[index];
                            const isCompleted = originalStep?.status === 'completed';
                            const isFailed = originalStep?.status === 'failed';
                            const isInProgress = originalStep?.status === 'in_progress';

                            return (
                                <div key={step.id || index} style={{
                                    display: 'flex',
                                    gap: '8px',
                                    marginBottom: '12px',
                                    padding: '12px',
                                    background: 'rgba(255, 255, 255, 0.03)',
                                    borderRadius: '8px',
                                    border: `1px solid ${isCompleted ? '#10b981' : isFailed ? '#ef4444' : isInProgress ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)'}`,
                                    alignItems: 'center'
                                }}>
                                    <span style={{
                                        fontWeight: 600,
                                        color: isCompleted ? '#10b981' : isFailed ? '#ef4444' : isInProgress ? '#3b82f6' : '#9ca3af',
                                        minWidth: '24px',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center'
                                    }}>
                                        {isCompleted ? <CheckCircle2 size={16} /> :
                                            isFailed ? <XCircle size={16} /> :
                                                isInProgress ? <Loader2 size={16} className="spinner" /> :
                                                    `${index + 1}.`}
                                    </span>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', gap: '8px' }}>
                                            <input
                                                type="text"
                                                value={step.description}
                                                onChange={(e) => handlePlanChange(index, 'description', e.target.value)}
                                                style={{
                                                    flex: 1,
                                                    padding: '8px',
                                                    border: '1px solid rgba(255, 255, 255, 0.1)',
                                                    background: 'rgba(0, 0, 0, 0.3)',
                                                    color: '#efefef',
                                                    borderRadius: '4px',
                                                    marginBottom: '8px',
                                                    fontSize: '0.9rem'
                                                }}
                                            />
                                            {/* Action Buttons */}
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                <button
                                                    onClick={() => handleAddStep(index + 1)}
                                                    title="Insert Step Below"
                                                    style={{
                                                        padding: '4px',
                                                        background: 'rgba(255, 255, 255, 0.1)',
                                                        border: 'none',
                                                        borderRadius: '4px',
                                                        cursor: 'pointer',
                                                        color: '#10b981'
                                                    }}
                                                >
                                                    <Plus size={14} />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteStep(index)}
                                                    title="Delete Step"
                                                    disabled={plan.length <= 1}
                                                    style={{
                                                        padding: '4px',
                                                        background: 'rgba(255, 255, 255, 0.1)',
                                                        border: 'none',
                                                        borderRadius: '4px',
                                                        cursor: plan.length <= 1 ? 'not-allowed' : 'pointer',
                                                        color: '#ef4444',
                                                        opacity: plan.length <= 1 ? 0.5 : 1
                                                    }}
                                                >
                                                    <Trash2 size={14} />
                                                </button>
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                                <div style={{ position: 'absolute', left: '8px', color: '#9ca3af', display: 'flex' }}>
                                                    {AGENT_ICONS[step.agent_type] || <Bot size={14} />}
                                                </div>
                                                <select
                                                    value={step.agent_type}
                                                    onChange={(e) => {
                                                        const newVal = e.target.value;
                                                        if (newVal === '__create_new__') {
                                                            setShowCreateAgentModal(true);
                                                        } else {
                                                            handlePlanChange(index, 'agent_type', newVal);
                                                        }
                                                    }}
                                                    style={{
                                                        padding: '4px 8px 4px 28px',
                                                        border: '1px solid rgba(255, 255, 255, 0.1)',
                                                        background: 'rgba(0, 0, 0, 0.3)',
                                                        color: '#efefef',
                                                        borderRadius: '4px',
                                                        fontSize: '0.875rem',
                                                        appearance: 'none',
                                                        cursor: 'pointer',
                                                        maxWidth: '150px'
                                                    }}
                                                >
                                                    {availableAgents.map(agent => (
                                                        <option key={agent.id} value={agent.id}>
                                                            {agent.name} {agent.type === 'custom' ? '(Custom)' : ''}
                                                        </option>
                                                    ))}
                                                    <option disabled>──────────</option>
                                                    <option value="__create_new__" style={{ fontStyle: 'italic', color: '#10b981' }}>+ Create New Agent...</option>
                                                </select>
                                            </div>
                                            {isCompleted && (
                                                <span style={{ fontSize: '0.75rem', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                    <AlertTriangle size={12} /> Editing will re-run this & downstream steps
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                ) : (
                    plan.length > 0 ? (
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesState}
                            onNodeClick={onNodeClick}
                            nodeTypes={nodeTypes}
                            fitView
                            attributionPosition="bottom-right"
                        >
                            <Background color="#333" gap={16} />
                            <Controls />
                        </ReactFlow>
                    ) : (
                        <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4b5563' }}>
                            Waiting for plan...
                        </div>
                    )
                )}
            </div>

            {
                selectedStep && (
                    <StepDetailModal
                        step={selectedStep}
                        logs={logs}
                        artifacts={artifacts}
                        onClose={() => setSelectedStep(null)}
                    />
                )
            }
            {
                showCreateAgentModal && (
                    <CreateAgentModal
                        onClose={() => setShowCreateAgentModal(false)}
                        onSave={(newAgentId) => {
                            // Refresh agents list
                            const url = apiBaseUrl ? `${apiBaseUrl}/api/agents` : '/api/agents';
                            fetch(url)
                                .then(res => res.json())
                                .then(data => setAvailableAgents(data))
                                .catch(err => console.error("Failed to load agents:", err));

                            // Select the new agent (if we knew which index... actually user just created it, 
                            // they can now select it from dropdown.
                            // To be smoother, we might want to pass the active index to this modal 
                            // but for now refresing list is enough)
                        }}
                    />
                )
            }
        </div >
    );
}
