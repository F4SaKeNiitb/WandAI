import { useState, useEffect, useCallback, useRef } from 'react';
import { Wand2, Bot } from 'lucide-react';
import { useWebSocket } from './hooks/useWebSocket';
import { RequestInput } from './components/RequestInput';
import { AgentStatusPanel } from './components/AgentStatusPanel';
import { PlanViewer } from './components/PlanViewer';
import { ResultDisplay } from './components/ResultDisplay';
import { ClarificationModal, ApprovalModal } from './components/ClarificationModal';
import { CreateAgentModal } from './components/CreateAgentModal';
import { LogsPanel } from './components/LogsPanel';
import { ConversationMode } from './components/ConversationMode';

// API basic configuration
const API_BASE_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

// API calls
async function submitRequest(request) {
    const response = await fetch(`${API_BASE_URL}/api/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            request,
            require_approval: false
        }),
    });
    return response.json();
}

async function submitClarifications(sessionId, clarifications) {
    const response = await fetch(`${API_BASE_URL}/api/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            clarifications
        }),
    });
    return response.json();
}

async function submitStepClarification(sessionId, stepId, clarifications) {
    const response = await fetch(`${API_BASE_URL}/api/step-clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            step_id: stepId,
            clarifications
        }),
    });
    return response.json();
}

async function submitApproval(sessionId, approved, modifications = null, newPlan = null) {
    const response = await fetch(`${API_BASE_URL}/api/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            approved,
            modifications,
            plan: newPlan
        }),
    });
    return response.json();
}

async function submitPlanUpdate(sessionId, plan) {
    const response = await fetch(`${API_BASE_URL}/api/plan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            plan
        }),
    });
    return response.json();
}

async function getSessionStatus(sessionId) {
    const response = await fetch(`${API_BASE_URL}/api/status/${sessionId}`);
    return response.json();
}

// Live Conversation & Refinement API calls
async function sendChatMessage(sessionId, message) {
    const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            message
        }),
    });
    return response.json();
}

async function sendRefinement(sessionId, refinement, keepArtifacts = true) {
    const response = await fetch(`${API_BASE_URL}/api/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            session_id: sessionId,
            refinement,
            keep_artifacts: keepArtifacts
        }),
    });
    return response.json();
}

async function getConversationHistory(sessionId) {
    const response = await fetch(`${API_BASE_URL}/api/conversation/${sessionId}`);
    return response.json();
}

function App() {
    // State
    const [sessionId, setSessionId] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [status, setStatus] = useState(null);
    const [plan, setPlan] = useState([]);
    const [currentStep, setCurrentStep] = useState(0);
    const [logs, setLogs] = useState([]);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [artifacts, setArtifacts] = useState([]);
    const [toolActivity, setToolActivity] = useState(null);

    // Conversation state
    const [conversationHistory, setConversationHistory] = useState([]); // Server state
    const [pendingMessages, setPendingMessages] = useState([]); // Optimistic local state

    // Modal states
    const [clarificationQuestions, setClarificationQuestions] = useState(null);
    const [stepClarificationData, setStepClarificationData] = useState(null); // { stepId, questions }
    const [showApprovalModal, setShowApprovalModal] = useState(false);
    const [showCreateAgentModal, setShowCreateAgentModal] = useState(false);
    const [isSubmittingClarification, setIsSubmittingClarification] = useState(false);

    // Forward ref for handleRefine to avoid circular dependencies
    const handleRefineRef = useRef(null);
    const isUpdatingPlan = useRef(false);

    // Helper to update history and remove matching pending messages
    const updateHistory = useCallback((newServerHistory) => {
        // DEBUG: Trace why history vanishes
        if (!newServerHistory || newServerHistory.length === 0) {
            console.warn("⚠️ App: updateHistory received EMPTY history!", newServerHistory);

            // PROTECTION: If we are actively running, don't wipe history based on a likely transient glitch
            if (status === 'executing' || status === 'planning') {
                console.log("🛡️ App: Ignoring empty history update while executing");
                return;
            }
        } else {
            console.log("✅ App: updateHistory received:", newServerHistory.length, "items");
        }

        setConversationHistory(newServerHistory || []);

        // Remove pending messages that are now in server history
        setPendingMessages(prev => prev.filter(pending => {
            // Check if this pending message is present in the new server history
            // We match by content and role
            const existsInServer = (newServerHistory || []).some(serverMsg =>
                serverMsg.role === pending.role &&
                serverMsg.content === pending.content
            );
            return !existsInServer;
        }));
    }, [status]);

    // WebSocket message handler
    const handleWebSocketMessage = useCallback((data) => {
        console.log('WS Event:', data);
        const { type } = data;

        // Update state based on event type
        if (data.status) {
            setStatus(data.status);
            // Reset submitting state if status changes from waiting_clarification
            // Reset submitting state ONLY if status definitively moves forward
            if (['planning', 'executing', 'completed', 'error', 'waiting_approval'].includes(data.status)) {
                setIsSubmittingClarification(false);
            }
        }

        if (data.plan && !isUpdatingPlan.current) {
            setPlan(data.plan);
        }

        if (data.current_step !== undefined) {
            setCurrentStep(data.current_step);
        }

        if (data.conversation_history) {
            updateHistory(data.conversation_history);
        }

        // Handle specific events
        switch (type) {
            case 'clarification_needed':
                if (!isSubmittingClarification) {
                    setClarificationQuestions(data.questions || []);
                    setIsLoading(false);
                }
                break;

            case 'step_clarification_needed':
                if (!isSubmittingClarification) {
                    setStepClarificationData({
                        stepId: data.step_id,
                        questions: data.questions || [],
                        agentType: data.agent_type
                    });
                    setIsLoading(false);
                }
                break;

            case 'approval_needed':
                setShowApprovalModal(true);
                setIsLoading(false);
                break;

            case 'execution_completed':
            case 'refinement_completed':
                setIsLoading(false);
                // Fetch final result
                if (sessionId) {
                    getSessionStatus(sessionId).then(res => {
                        setResult(res.final_response);
                        setArtifacts(res.artifacts || []);
                        setStatus(res.status);
                    });
                    // Also fetch conversation history
                    getConversationHistory(sessionId).then(res => {
                        updateHistory(res.conversation || []);
                    });
                }
                break;

            case 'chat_response':
                // Update conversation history with new response
                setConversationHistory(prev => [...prev, {
                    role: 'assistant',
                    content: data.response,
                    type: 'chat'
                }]);
                break;

            case 'refinement_intent_detected':
                // Automatically trigger refinement flow
                if (data.refinement) {
                    if (handleRefineRef.current) {
                        handleRefineRef.current(data.refinement);
                    }
                }
                break;

            case 'refinement_started':
                setIsLoading(true);
                setStatus('planning');
                break;

            case 'step_failed':
            case 'agent_failed':
                // Continue processing, the orchestrator will handle retries
                break;

            case 'searching':
                // Handle tool usage events
                setToolActivity({
                    agent: data.agent_type,
                    tool: data.tool,
                    query: data.query,
                    timestamp: Date.now()
                });

                // Clear after a delay to avoid stale state
                setTimeout(() => {
                    setToolActivity(prev => {
                        if (prev && Date.now() - prev.timestamp > 4000) {
                            return null;
                        }
                        return prev;
                    });
                }, 5000);
                break;

            default:
                // Update logs from latest_log if available
                if (data.latest_log) {
                    setLogs(prev => [...prev, data.latest_log]);
                }
        }
    }, [sessionId, isSubmittingClarification, updateHistory]); // Dependencies

    // WebSocket connection
    const { isConnected, subscribe, clearMessages } = useWebSocket(null, handleWebSocketMessage);


    // Poll for status updates (backup for WebSocket)
    useEffect(() => {
        if (!sessionId) return;

        const interval = setInterval(async () => {
            try {
                const statusData = await getSessionStatus(sessionId);
                setStatus(statusData.status);

                // Reset submitting state ONLY if status definitively moves forward
                if (['planning', 'executing', 'completed', 'error', 'waiting_approval'].includes(statusData.status)) {
                    setIsSubmittingClarification(false);
                }

                if (!isUpdatingPlan.current) {
                    setPlan(statusData.plan || []);
                }
                setCurrentStep(statusData.current_step || 0);
                setLogs(statusData.logs || []);
                if (statusData.conversation_history) {
                    updateHistory(statusData.conversation_history);
                }

                if (statusData.status === 'completed') {
                    setResult(statusData.final_response);
                    setArtifacts(statusData.artifacts || []);
                    if (status !== 'planning' && status !== 'executing') {
                        // Only turn off loading if we are truly done and not restarted
                        setIsLoading(false);
                    }
                } else if (statusData.status === 'error') {
                    setError(statusData.error_message);
                    setIsLoading(false);
                } else if (statusData.status === 'waiting_clarification') {
                    if (!isSubmittingClarification) {
                        setClarificationQuestions(statusData.clarifying_questions || []);
                        setIsLoading(false);
                    }
                } else if (statusData.status === 'waiting_step_clarification') {
                    if (!isSubmittingClarification) {
                        setStepClarificationData({
                            stepId: statusData.step_clarification_step_id,
                            questions: statusData.step_clarification_questions || [],
                            agentType: 'Agent' // Default, maybe enhance API to return agent type
                        });
                        setIsLoading(false);
                    }
                } else if (statusData.status === 'waiting_approval') {
                    setShowApprovalModal(true);
                    setIsLoading(false);
                }
            } catch (e) {
                console.error('Failed to fetch status:', e);
            }
        }, 2000);

        return () => clearInterval(interval);
    }, [sessionId, isSubmittingClarification, status, updateHistory]);

    // Handle request submission
    const handleSubmit = useCallback(async (request) => {
        // Reset state
        setIsLoading(true);
        setResult(null);
        setError(null);
        setPlan([]);
        setLogs([]);
        setArtifacts([]);
        setCurrentStep(0);
        setStatus('pending');
        setIsSubmittingClarification(false);
        setConversationHistory([]);
        setPendingMessages([]); // Clear pending
        clearMessages();

        try {
            const response = await submitRequest(request);

            if (response.session_id) {
                setSessionId(response.session_id);
                subscribe(response.session_id);
            } else {
                setError('Failed to submit request');
                setIsLoading(false);
            }
        } catch (e) {
            setError('Failed to connect to server: ' + e.message);
            setIsLoading(false);
        }
    }, [subscribe, clearMessages]);

    // Handle clarification submission
    const handleClarificationSubmit = useCallback(async (answers) => {
        setClarificationQuestions(null);
        setIsSubmittingClarification(true);
        setIsLoading(true);

        try {
            await submitClarifications(sessionId, answers);
        } catch (e) {
            setError('Failed to submit clarifications: ' + e.message);
            setIsLoading(false);
            setIsSubmittingClarification(false);
        }
    }, [sessionId]);

    // Handle step clarification submission
    const handleStepClarificationSubmit = useCallback(async (answers) => {
        const stepId = stepClarificationData?.stepId;
        setStepClarificationData(null);
        setIsSubmittingClarification(true);
        setIsLoading(true);

        try {
            await submitStepClarification(sessionId, stepId, answers);
        } catch (e) {
            setError('Failed to submit step clarifications: ' + e.message);
            setIsLoading(false);
            setIsSubmittingClarification(false);
        }
    }, [sessionId, stepClarificationData]);

    // Handle plan approval
    const handleApprove = useCallback(async (customPlan = null) => {
        setShowApprovalModal(false);
        setIsLoading(true);

        try {
            await submitApproval(sessionId, true, null, customPlan);
        } catch (e) {
            setError('Failed to submit approval: ' + e.message);
            setIsLoading(false);
        }
    }, [sessionId]);

    // Handle mid-execution plan update
    const handleUpdatePlan = useCallback(async (newPlan) => {
        isUpdatingPlan.current = true;
        try {
            // Check if any completed steps were modified (will trigger re-execution)
            const hasCompletedChanges = plan.some((oldStep, index) => {
                const newStep = newPlan[index];
                if (!newStep) return false;
                const wasCompleted = oldStep.status === 'completed' || oldStep.status === 'failed';
                const hasChanged = oldStep.description !== newStep.description ||
                    oldStep.agent_type !== newStep.agent_type;
                return wasCompleted && hasChanged;
            });

            // If editing completed steps or status was 'completed', trigger loading state
            if (hasCompletedChanges || status === 'completed') {
                setIsLoading(true);
                setStatus('executing');  // Reset status to show we're re-executing
            }

            // Optimistically update the plan to prevent UI flicker/reversion
            setPlan(newPlan);

            await submitPlanUpdate(sessionId, newPlan);

            // Keep the lock for a moment to prevent immediate overwrite by lagging poll/WS
            setTimeout(() => {
                isUpdatingPlan.current = false;
            }, 2000);

            // WebSocket/polling will eventually bring back the authoritative state (with updated statuses if re-run triggered)
        } catch (e) {
            isUpdatingPlan.current = false;
            setError('Failed to update plan: ' + e.message);
            setIsLoading(false);
        }
    }, [sessionId, plan, status]);

    // Handle plan modification
    const handleModify = useCallback(async (modifications) => {
        setShowApprovalModal(false);
        setIsLoading(true);

        try {
            await submitApproval(sessionId, false, modifications);
        } catch (e) {
            setError('Failed to submit modifications: ' + e.message);
            setIsLoading(false);
        }
    }, [sessionId]);

    // Handle chat message (Live Conversation Mode)
    const handleSendMessage = useCallback(async (message) => {
        if (!sessionId) return;

        // Add to pending messages instead of main history
        setPendingMessages(prev => [...prev, {
            role: 'user',
            content: message,
            type: 'chat'
        }]);

        // Indicate loading to encourage polling/show activity
        setIsLoading(true);

        try {
            await sendChatMessage(sessionId, message);
        } catch (e) {
            console.error('Failed to send chat message:', e);
            setIsLoading(false);
        }
    }, [sessionId]);

    const handleRefine = useCallback(async (refinement) => {
        if (!sessionId) return;

        // Add to pending messages
        setPendingMessages(prev => [...prev, {
            role: 'user',
            content: `[Refinement]: ${refinement}`,
            type: 'refinement'
        }]);

        setIsLoading(true);
        setStatus('planning');

        try {
            await sendRefinement(sessionId, refinement, true);
        } catch (e) {
            setError('Failed to submit refinement: ' + e.message);
            setIsLoading(false);
        }
    }, [sessionId]);

    // Update the ref whenever handleRefine changes
    useEffect(() => {
        handleRefineRef.current = handleRefine;
    }, [handleRefine]);

    return (
        <div className="app-container">
            {/* Header */}
            <header className="header">
                <div className="logo">
                    <Wand2 className="logo-icon" size={32} />
                    <div>
                        <div className="logo-text">WandAI</div>
                        <div className="logo-subtitle">Multi-Agent Orchestration</div>
                    </div>
                </div>

                <div className="connection-status">
                    <button
                        onClick={() => setShowCreateAgentModal(true)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            background: 'rgba(255,255,255,0.1)',
                            border: '1px solid rgba(255,255,255,0.2)',
                            borderRadius: '20px',
                            padding: '6px 12px',
                            color: '#e2e8f0',
                            cursor: 'pointer',
                            fontSize: '0.85rem',
                            marginRight: '16px'
                        }}
                    >
                        <Bot size={14} />
                        <span>Agents</span>
                    </button>
                    <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></div>
                    <span>{isConnected ? 'Connected' : 'Connecting...'}</span>
                </div>
            </header>

            {/* Main Content */}
            <main className="main-content">
                {/* Left Column - Request & Results */}
                <div className="request-section">
                    <RequestInput
                        onSubmit={handleSubmit}
                        isLoading={isLoading}
                    />

                    <ResultDisplay
                        status={status}
                        result={result}
                        error={error}
                        artifacts={artifacts}
                    />
                </div>

                {/* Right Column - Agent Status & Plan */}
                <div className="sidebar">
                    <AgentStatusPanel
                        plan={plan}
                        currentStep={currentStep}
                        logs={logs}
                        toolActivity={toolActivity}
                    />

                    <PlanViewer
                        plan={plan}
                        currentStep={currentStep}
                        onUpdatePlan={handleUpdatePlan}
                        isEditable={status === 'executing' || status === 'planning' || status === 'completed'}
                        logs={logs}
                        artifacts={artifacts}
                        apiBaseUrl={API_BASE_URL}
                    />

                    <ConversationMode
                        sessionId={sessionId}
                        isActive={!!sessionId}
                        status={status}
                        conversationHistory={[...conversationHistory, ...pendingMessages]}
                        onSendMessage={handleSendMessage}
                        onRefine={handleRefine}
                    />

                    <LogsPanel logs={logs} />
                </div>
            </main>

            {/* Modals */}
            {clarificationQuestions && clarificationQuestions.length > 0 && (
                <ClarificationModal
                    questions={clarificationQuestions}
                    onSubmit={handleClarificationSubmit}
                    onCancel={() => {
                        setClarificationQuestions(null);
                        setIsLoading(false);
                    }}
                />
            )}

            {stepClarificationData && stepClarificationData.questions.length > 0 && (
                <ClarificationModal
                    questions={stepClarificationData.questions}
                    title="Agent Needs Help 🤖"
                    description={`One of the agents is stuck on step '${stepClarificationData.stepId}' and needs your help to proceed:`}
                    onSubmit={handleStepClarificationSubmit}
                    onCancel={() => {
                        // If cancelled, we can't really do anything but maybe clear local state
                        // The backend is still waiting.
                        setStepClarificationData(null);
                        setIsLoading(false);
                    }}
                />
            )}

            {showApprovalModal && (
                <ApprovalModal
                    plan={plan}
                    onApprove={handleApprove}
                    onModify={handleModify}
                    onCancel={() => {
                        setShowApprovalModal(false);
                        setIsLoading(false);
                    }}
                />
            )}

            {showCreateAgentModal && (
                <CreateAgentModal
                    onClose={() => setShowCreateAgentModal(false)}
                    onSave={(newAgentId) => {
                        // Just close, next query will pick up new agent
                        console.log("Created agent:", newAgentId);
                    }}
                />
            )}
        </div>
    );
}

export default App;
