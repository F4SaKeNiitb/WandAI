/**
 * Simple markdown renderer for the result display.
 * Handles basic markdown formatting.
 */
export function renderMarkdown(text) {
    if (!text) return null;

    // Split into lines and process
    const lines = text.split('\n');
    const elements = [];
    let inCodeBlock = false;
    let codeContent = [];
    let codeLanguage = '';

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Code blocks
        if (line.startsWith('```')) {
            if (inCodeBlock) {
                elements.push(
                    <pre key={`code-${i}`} className="code-block">
                        <code>{codeContent.join('\n')}</code>
                    </pre>
                );
                codeContent = [];
                inCodeBlock = false;
            } else {
                inCodeBlock = true;
                codeLanguage = line.slice(3);
            }
            continue;
        }

        if (inCodeBlock) {
            codeContent.push(line);
            continue;
        }

        // Headers
        if (line.startsWith('### ')) {
            elements.push(<h3 key={i}>{processInline(line.slice(4))}</h3>);
        } else if (line.startsWith('## ')) {
            elements.push(<h2 key={i}>{processInline(line.slice(3))}</h2>);
        } else if (line.startsWith('# ')) {
            elements.push(<h1 key={i}>{processInline(line.slice(2))}</h1>);
        }
        // Lists
        else if (line.match(/^[-*] /)) {
            elements.push(
                <li key={i} style={{ marginLeft: '1.5rem' }}>
                    {processInline(line.slice(2))}
                </li>
            );
        } else if (line.match(/^\d+\. /)) {
            elements.push(
                <li key={i} style={{ marginLeft: '1.5rem', listStyleType: 'decimal' }}>
                    {processInline(line.replace(/^\d+\. /, ''))}
                </li>
            );
        }
        // Horizontal rule
        else if (line.match(/^---+$/)) {
            elements.push(<hr key={i} style={{ border: 'none', borderTop: '1px solid var(--color-bg-hover)', margin: '1rem 0' }} />);
        }
        // Regular paragraph
        else if (line.trim()) {
            elements.push(<p key={i}>{processInline(line)}</p>);
        }
        // Empty line
        else {
            elements.push(<br key={i} />);
        }
    }

    return elements;
}

function escapeHtml(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function processInline(text) {
    text = escapeHtml(text);
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Inline code
    text = text.replace(/`(.+?)`/g, '<code class="inline-code">$1</code>');

    return <span dangerouslySetInnerHTML={{ __html: text }} />;
}

import { FileText, Bot, AlertTriangle, Download } from 'lucide-react';

export function ResultDisplay({ status, result, error, artifacts, streamingText, isStreaming }) {
    const hasCharts = artifacts?.some(a => a.type === 'chart' || a.type === 'image');

    const handleDownload = () => {
        if (!result) return;
        const blob = new Blob([result], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `wandai-report-${new Date().toISOString().slice(0, 10)}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    return (
        <div className="result-section glass-panel">
            <div className="result-header">
                <h3><span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}><FileText size={18} /> Result</span></h3>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {result && (
                        <button
                            onClick={handleDownload}
                            title="Download Report"
                            style={{
                                background: 'transparent',
                                border: 'none',
                                color: 'var(--color-text-secondary)',
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                padding: '4px',
                                borderRadius: '4px',
                                transition: 'color 0.2s'
                            }}
                            onMouseEnter={(e) => e.target.style.color = 'var(--color-text-primary)'}
                            onMouseLeave={(e) => e.target.style.color = 'var(--color-text-secondary)'}
                        >
                            <Download size={16} />
                        </button>
                    )}
                    <span className={`status-badge ${status}`}>
                        {status?.replace('_', ' ') || 'pending'}
                    </span>
                </div>
            </div>
            <div className="result-content">
                {!result && !error && status !== 'completed' && (
                    <div className="empty-state">
                        <div className="empty-state-icon">
                            <Bot size={48} strokeWidth={1.5} color="#4b5563" />
                        </div>
                        <h4>Ready to Execute</h4>
                        <p>Submit a request above to see results here</p>
                    </div>
                )}

                {isStreaming && streamingText && !result && (
                    <div className="result-markdown streaming">
                        {renderMarkdown(streamingText)}
                        <span className="streaming-cursor">|</span>
                    </div>
                )}

                {error && (
                    <div style={{
                        color: 'var(--color-error)',
                        padding: '1rem',
                        background: 'rgba(239, 68, 68, 0.1)',
                        borderRadius: 'var(--radius-md)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px'
                    }}>
                        <AlertTriangle size={20} /> {error}
                    </div>
                )}

                {result && (
                    <div className="result-markdown">
                        {renderMarkdown(result)}
                    </div>
                )}

                {hasCharts && artifacts
                    .filter(a => a.type === 'chart' || a.type === 'image')
                    .map((artifact, index) => (
                        <div key={index} className="chart-container">
                            {artifact.content?.image_base64 ? (
                                <img
                                    src={`data:image/png;base64,${artifact.content.image_base64}`}
                                    alt={artifact.name || 'Chart'}
                                />
                            ) : (
                                <div style={{
                                    height: '200px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    background: 'rgba(255,255,255,0.05)',
                                    color: 'var(--color-text-muted)',
                                    borderRadius: 'var(--radius-md)',
                                    fontSize: '0.875rem'
                                }}>
                                    Chart image not available
                                </div>
                            )}
                            {artifact.content?.title && (
                                <p style={{
                                    textAlign: 'center',
                                    color: 'var(--color-text-muted)',
                                    fontSize: '0.875rem',
                                    marginTop: '0.5rem'
                                }}>
                                    {artifact.content.title}
                                </p>
                            )}
                        </div>
                    ))
                }
            </div>
        </div>
    );
}
