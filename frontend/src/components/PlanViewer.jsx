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
import dagre from 'dagre';
import { Edit2, Save, X, Loader2, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

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

export function PlanViewer({ plan, currentStep, onUpdatePlan, isEditable }) {
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesState] = useEdgesState([]);
    const [selectedStep, setSelectedStep] = useState(null);
    const [isEditing, setIsEditing] = useState(false);
    const [editedPlan, setEditedPlan] = useState([]);

    // Sync edited plan when entering edit mode
    useEffect(() => {
        if (isEditing && plan) {
            setEditedPlan(JSON.parse(JSON.stringify(plan)));
        }
    }, [isEditing]);

    const handlePlanChange = (index, field, value) => {
        const newPlan = [...editedPlan];
        newPlan[index][field] = value;
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
        <div className="plan-viewer" style={{ height: '500px', background: '#0a0a0a', borderRadius: '12px', border: '1px solid #333' }}>
            <div style={{
                padding: '16px',
                borderBottom: '1px solid #222',
                background: '#111',
                borderTopLeftRadius: '12px',
                borderTopRightRadius: '12px',
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
                                background: '#333',
                                color: '#efefef',
                                borderRadius: '4px',
                                border: 'none',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px'
                            }}
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
                                    padding: '8px',
                                    background: '#1a1a1a',
                                    borderRadius: '6px',
                                    border: `1px solid ${isCompleted ? '#10b981' : isFailed ? '#ef4444' : isInProgress ? '#3b82f6' : '#333'}`,
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
                                        <input
                                            type="text"
                                            value={step.description}
                                            onChange={(e) => handlePlanChange(index, 'description', e.target.value)}
                                            style={{
                                                width: '100%',
                                                padding: '6px',
                                                border: '1px solid #333',
                                                background: '#222',
                                                color: '#efefef',
                                                borderRadius: '4px',
                                                marginBottom: '4px'
                                            }}
                                        />
                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                                            <select
                                                value={step.agent_type}
                                                onChange={(e) => handlePlanChange(index, 'agent_type', e.target.value)}
                                                style={{
                                                    padding: '4px',
                                                    border: '1px solid #333',
                                                    background: '#222',
                                                    color: '#efefef',
                                                    borderRadius: '4px',
                                                    fontSize: '0.875rem'
                                                }}
                                            >
                                                <option value="researcher">Researcher</option>
                                                <option value="coder">Coder</option>
                                                <option value="analyst">Analyst</option>
                                                <option value="writer">Writer</option>
                                                <option value="orchestrator">Orchestrator</option>
                                            </select>
                                            {isCompleted && (
                                                <span style={{ fontSize: '0.7rem', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '4px' }}>
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

            {selectedStep && (
                <StepDetailModal
                    step={selectedStep}
                    onClose={() => setSelectedStep(null)}
                />
            )}
        </div>
    );
}
