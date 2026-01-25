import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { RequestInput } from './components/RequestInput';
import { AgentStatusPanel } from './components/AgentStatusPanel';
import { PlanViewer } from './components/PlanViewer';
import { ResultDisplay } from './components/ResultDisplay';
import { ClarificationModal, ApprovalModal } from './components/ClarificationModal';
import { LogsPanel } from './components/LogsPanel';
import { ConversationMode } from './components/ConversationMode';

// API basic configuration
const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

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

    // Conversation state (stretch goals)
    const [conversationHistory, setConversationHistory] = useState([]);

    // Modal states
    const [clarificationQuestions, setClarificationQuestions] = useState(null);
    const [showApprovalModal, setShowApprovalModal] = useState(false);
    const [isSubmittingClarification, setIsSubmittingClarification] = useState(false);

    // WebSocket connection
    const { isConnected, lastMessage, subscribe, clearMessages } = useWebSocket();

    // Handle incoming WebSocket messages
    useEffect(() => {
        if (!lastMessage) return;

        console.log('WS Event:', lastMessage);

        const { type, ...data } = lastMessage;

        // Update state based on event type
        if (data.status) {
            setStatus(data.status);
            // Reset submitting state if status changes from waiting_clarification
            // Reset submitting state ONLY if status definitively moves forward
            if (['planning', 'executing', 'completed', 'error', 'waiting_approval'].includes(data.status)) {
                setIsSubmittingClarification(false);
            }
        }

        if (data.plan) {
            setPlan(data.plan);
        }

        if (data.current_step !== undefined) {
            setCurrentStep(data.current_step);
        }

        // Handle specific events
        switch (type) {
            case 'clarification_needed':
                if (!isSubmittingClarification) {
                    setClarificationQuestions(data.questions || []);
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
                        setConversationHistory(res.conversation || []);
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

            case 'refinement_started':
                setIsLoading(true);
                setStatus('planning');
                break;

            case 'step_failed':
            case 'agent_failed':
                // Continue processing, the orchestrator will handle retries
                break;

            default:
                // Update logs from latest_log if available
                if (data.latest_log) {
                    setLogs(prev => [...prev, data.latest_log]);
                }
        }
    }, [lastMessage, sessionId, isSubmittingClarification]);

    // Poll for status updates (backup for WebSocket)
    useEffect(() => {
        if (!sessionId || !isLoading) return;

        const interval = setInterval(async () => {
            try {
                const statusData = await getSessionStatus(sessionId);
                setStatus(statusData.status);

                // Reset submitting state ONLY if status definitively moves forward
                if (['planning', 'executing', 'completed', 'error', 'waiting_approval'].includes(statusData.status)) {
                    setIsSubmittingClarification(false);
                }

                setPlan(statusData.plan || []);
                setCurrentStep(statusData.current_step || 0);
                setLogs(statusData.logs || []);
                if (statusData.conversation_history) {
                    setConversationHistory(statusData.conversation_history);
                }

                if (statusData.status === 'completed') {
                    setResult(statusData.final_response);
                    setArtifacts(statusData.artifacts || []);
                    setIsLoading(false);
                } else if (statusData.status === 'error') {
                    setError(statusData.error_message);
                    setIsLoading(false);
                } else if (statusData.status === 'waiting_clarification') {
                    if (!isSubmittingClarification) {
                        setClarificationQuestions(statusData.clarifying_questions || []);
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
    }, [sessionId, isLoading, isSubmittingClarification]);

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
        setIsLoading(true);
        try {
            await submitPlanUpdate(sessionId, newPlan);
            setPlan(newPlan);
            setIsLoading(false);
        } catch (e) {
            setError('Failed to update plan: ' + e.message);
            setIsLoading(false);
        }
    }, [sessionId]);

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

        // Optimistically add user message to history
        setConversationHistory(prev => [...prev, {
            role: 'user',
            content: message,
            type: 'chat'
        }]);

        try {
            await sendChatMessage(sessionId, message);
        } catch (e) {
            console.error('Failed to send chat message:', e);
        }
    }, [sessionId]);

    // Handle refinement request (Multi-turn Refinement)
    const handleRefine = useCallback(async (refinement) => {
        if (!sessionId) return;

        // Add refinement to history
        setConversationHistory(prev => [...prev, {
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

    return (
        <div className="app-container">
            {/* Header */}
            <header className="header">
                <div className="logo">
                    <div className="logo-icon">🪄</div>
                    <div>
                        <div className="logo-text">WandAI</div>
                        <div className="logo-subtitle">Multi-Agent Orchestration</div>
                    </div>
                </div>

                <div className="connection-status">
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
                    />

                    <PlanViewer
                        plan={plan}
                        currentStep={currentStep}
                        onUpdatePlan={handleUpdatePlan}
                        isEditable={status === 'executing' || status === 'planning'}
                    />

                    <ConversationMode
                        sessionId={sessionId}
                        isActive={!!sessionId}
                        status={status}
                        conversationHistory={conversationHistory}
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
        </div>
    );
}

export default App;
