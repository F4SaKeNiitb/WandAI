import { BaseEdge, getBezierPath } from 'reactflow';
import { useEffect, useRef } from 'react';

/**
 * Custom animated edge that shows a flowing arrow when active.
 * Uses native SVG animation for better performance.
 */
export function AnimatedEdge({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style = {},
    markerEnd,
    data,
}) {
    const [edgePath] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
    });

    const isActive = data?.isActive;
    const isCompleted = data?.isCompleted;

    // Colors for active and completed states
    const activeColor = '#3b82f6';  // Blue
    const completedColor = '#10b981';  // Green
    const inactiveColor = '#333';

    const edgeColor = isActive ? activeColor : isCompleted ? completedColor : inactiveColor;

    return (
        <>
            {/* Intense Glow effect for active edges */}
            {isActive && (
                <>
                    {/* Outer soft glow */}
                    <path
                        d={edgePath}
                        style={{
                            fill: 'none',
                            opacity: 0.2, // Reduced from 0.3
                            filter: `blur(8px)`,
                            transition: 'opacity 0.3s ease',
                            pointerEvents: 'none',
                        }}
                    />
                    {/* Inner intense glow - Reduced width */}
                    <path
                        d={edgePath}
                        style={{
                            stroke: activeColor,
                            strokeWidth: 4, // Reduced from 8
                            fill: 'none',
                            opacity: 0.4, // Reduced from 0.6
                            filter: `blur(3px)`,
                            transition: 'opacity 0.3s ease',
                            pointerEvents: 'none',
                        }}
                    />
                </>
            )}

            {/* Base edge path */}
            <path
                id={id}
                className="react-flow__edge-path"
                d={edgePath}
                style={{
                    ...style,
                    stroke: edgeColor,
                    strokeWidth: isActive ? 2 : isCompleted ? 2 : 1, // Reduced active width from 3 to 2
                    fill: 'none',
                    filter: isActive ? `drop-shadow(0 0 2px ${activeColor})` : 'none', // Reduced shadow
                }}
                markerEnd={markerEnd}
            />

            {/* Animated circle that moves along the path when active */}
            {isActive && (
                <>
                    {/* Animated dot 1 - Slower speed */}
                    <circle r="4" fill={activeColor} filter={`drop-shadow(0 0 4px ${activeColor})`}>
                        <animateMotion
                            dur="3s" // Slowed from 1.5s
                            repeatCount="indefinite"
                            path={edgePath}
                        />
                    </circle>
                    {/* Animated dot 2 (offset) - Removed dot 3 entirely */}
                    <circle r="3" fill={activeColor} opacity="0.5" filter={`drop-shadow(0 0 2px ${activeColor})`}>
                        <animateMotion
                            dur="3s" // Slowed from 1.5s
                            repeatCount="indefinite"
                            path={edgePath}
                            begin="1.5s" // Adjusted timing
                        />
                    </circle>
                </>
            )}

            {/* Static checkmark indicator when completed */}
            {isCompleted && !isActive && (
                <g transform={`translate(${(sourceX + targetX) / 2 - 8}, ${(sourceY + targetY) / 2 - 8})`}>
                    <circle cx="8" cy="8" r="8" fill={completedColor} filter={`drop-shadow(0 0 3px ${completedColor})`} />
                    <path
                        d="M5 8l2 2 4-4"
                        stroke="white"
                        strokeWidth="1.5"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    />
                </g>
            )}
        </>
    );
}

export const edgeTypes = {
    animated: AnimatedEdge,
};
