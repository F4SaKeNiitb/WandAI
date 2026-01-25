import { useState } from 'react';

export function ClarificationModal({ questions, onSubmit, onCancel }) {
    const [answers, setAnswers] = useState(questions.map(() => ''));

    const handleAnswerChange = (index, value) => {
        const newAnswers = [...answers];
        newAnswers[index] = value;
        setAnswers(newAnswers);
    };

    const handleSubmit = () => {
        const filledAnswers = answers.filter(a => a.trim());
        if (filledAnswers.length > 0) {
            onSubmit(filledAnswers);
        }
    };

    const allAnswered = answers.every(a => a.trim());

    return (
        <div className="modal-overlay" onClick={onCancel}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h3>Clarification Needed</h3>
                </div>
                <div className="modal-body">
                    <p style={{
                        color: 'var(--color-text-secondary)',
                        marginBottom: '1rem',
                        fontSize: '0.875rem'
                    }}>
                        Your request needs some clarification. Please answer the following questions:
                    </p>

                    {questions.map((question, index) => (
                        <div key={index} className="clarification-question">
                            <label style={{ fontWeight: 500 }}>
                                {index + 1}. {question}
                            </label>
                            <input
                                type="text"
                                className="clarification-input"
                                placeholder="Your answer..."
                                value={answers[index]}
                                onChange={(e) => handleAnswerChange(index, e.target.value)}
                                autoFocus={index === 0}
                            />
                        </div>
                    ))}
                </div>
                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onCancel}>
                        Cancel
                    </button>
                    <button
                        className="btn btn-primary"
                        onClick={handleSubmit}
                        disabled={!allAnswered}
                    >
                        Submit Clarifications
                    </button>
                </div>
            </div>
        </div>
    );
}

export function ApprovalModal({ plan, onApprove, onModify, onCancel }) {
    const [modifications, setModifications] = useState('');
    const [showModify, setShowModify] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editedPlan, setEditedPlan] = useState(plan ? JSON.parse(JSON.stringify(plan)) : []);

    const handleModify = () => {
        if (modifications.trim()) {
            onModify(modifications.trim());
        }
    };

    const handlePlanChange = (index, field, value) => {
        const newPlan = [...editedPlan];
        newPlan[index][field] = value;
        setEditedPlan(newPlan);
    };

    const handleSaveAndApprove = () => {
        onApprove(editedPlan);
    };

    return (
        <div className="modal-overlay" onClick={onCancel}>
            <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '800px' }}>
                <div className="modal-header">
                    <h3>{isEditing ? '✏️ Edit Plan' : '📋 Plan Approval'}</h3>
                </div>
                <div className="modal-body">
                    <p style={{
                        color: 'var(--color-text-secondary)',
                        marginBottom: '1rem',
                        fontSize: '0.875rem'
                    }}>
                        {isEditing
                            ? "Modify the steps below directly. Changes will be executed immediately."
                            : "Review the execution plan before proceeding:"}
                    </p>

                    <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                        {!isEditing ? (
                            plan?.map((step, index) => (
                                <div key={step.id} className="plan-step">
                                    <div className="step-number">{index + 1}</div>
                                    <div className="step-content">
                                        <div className="step-description">{step.description}</div>
                                        <div className="step-agent">🤖 {step.agent_type}</div>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div className="plan-editor">
                                {editedPlan.map((step, index) => (
                                    <div key={step.id} style={{
                                        display: 'flex',
                                        gap: '8px',
                                        marginBottom: '12px',
                                        padding: '8px',
                                        background: '#f9fafb',
                                        borderRadius: '6px',
                                        alignItems: 'center'
                                    }}>
                                        <span style={{ fontWeight: 600, color: '#6b7280', minWidth: '24px' }}>{index + 1}.</span>
                                        <div style={{ flex: 1 }}>
                                            <input
                                                type="text"
                                                value={step.description}
                                                onChange={(e) => handlePlanChange(index, 'description', e.target.value)}
                                                style={{
                                                    width: '100%',
                                                    padding: '6px',
                                                    border: '1px solid #d1d5db',
                                                    borderRadius: '4px',
                                                    marginBottom: '4px'
                                                }}
                                                placeholder="Step description..."
                                            />
                                            <select
                                                value={step.agent_type}
                                                onChange={(e) => handlePlanChange(index, 'agent_type', e.target.value)}
                                                style={{
                                                    padding: '4px',
                                                    border: '1px solid #d1d5db',
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
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {showModify && !isEditing && (
                        <div style={{ marginTop: '1rem' }}>
                            <label style={{
                                fontSize: '0.875rem',
                                color: 'var(--color-text-secondary)',
                                display: 'block',
                                marginBottom: '0.5rem'
                            }}>
                                Describe your modifications (Autopilot):
                            </label>
                            <textarea
                                className="request-input"
                                style={{ minHeight: '80px' }}
                                placeholder="e.g., 'Also include a comparison with competitor data'"
                                value={modifications}
                                onChange={(e) => setModifications(e.target.value)}
                            />
                        </div>
                    )}
                </div>
                <div className="modal-footer">
                    <button className="btn btn-secondary" onClick={onCancel}>
                        Cancel
                    </button>

                    {isEditing ? (
                        <>
                            <div style={{ flex: 1 }}></div>
                            <button className="btn btn-secondary" onClick={() => setIsEditing(false)}>
                                Back to Review
                            </button>
                            <button className="btn btn-primary" onClick={handleSaveAndApprove}>
                                ✓ Save & Execute
                            </button>
                        </>
                    ) : (
                        !showModify ? (
                            <>
                                <button className="btn btn-secondary" onClick={() => setIsEditing(true)}>
                                    ✏️ Edit Steps
                                </button>
                                <button
                                    className="btn btn-secondary"
                                    onClick={() => setShowModify(true)}
                                >
                                    Modify Request
                                </button>
                                <button className="btn btn-primary" onClick={() => onApprove(null)}>
                                    ✓ Approve & Execute
                                </button>
                            </>
                        ) : (
                            <button
                                className="btn btn-primary"
                                onClick={handleModify}
                                disabled={!modifications.trim()}
                            >
                                Submit Modifications
                            </button>
                        )
                    )}
                </div>
            </div>
        </div>
    );
}
