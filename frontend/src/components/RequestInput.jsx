import { useState } from 'react';

const EXAMPLE_REQUESTS = [
    "What's the current stock price of Apple and create a summary?",
    "Calculate the compound interest on $10,000 at 5% for 10 years",
    "Summarize the top tech news from this week",
    "Create a Python script to analyze a CSV file"
];

export function RequestInput({ onSubmit, isLoading }) {
    const [request, setRequest] = useState('');
    const handleSubmit = (e) => {
        e.preventDefault();
        if (request.trim() && !isLoading) {
            onSubmit(request.trim());
        }
    };

    const handleExampleClick = (example) => {
        setRequest(example);
    };

    return (
        <div className="input-card">
            <div className="input-header">
                <h2>🪄 New Request</h2>
                <p>Describe what you'd like to accomplish in plain language</p>
            </div>

            <form onSubmit={handleSubmit}>
                <textarea
                    className="request-input"
                    placeholder="e.g., 'Summarize the last 3 quarters' financial trends and create a chart' or 'Get Tesla's stock price for the last week and plot it'"
                    value={request}
                    onChange={(e) => setRequest(e.target.value)}
                    disabled={isLoading}
                />

                <div className="input-actions">
                    <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={!request.trim() || isLoading}
                    >
                        {isLoading ? (
                            <>
                                <span className="spinner"></span>
                                Processing...
                            </>
                        ) : (
                            <>
                                ✨ Execute Request
                            </>
                        )}
                    </button>
                </div>
            </form>

            <div className="examples">
                <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginRight: '0.5rem' }}>
                    Try:
                </span>
                {EXAMPLE_REQUESTS.map((example, index) => (
                    <button
                        key={index}
                        className="example-chip"
                        onClick={() => handleExampleClick(example)}
                        disabled={isLoading}
                    >
                        {example.length > 50 ? example.substring(0, 47) + '...' : example}
                    </button>
                ))}
            </div>
        </div>
    );
}
