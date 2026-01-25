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
                            stroke: activeColor,
                            strokeWidth: 20,
                            fill: 'none',
                            opacity: 0.3,
                            filter: `blur(8px)`,
                            transition: 'opacity 0.3s ease',
                            pointerEvents: 'none', // Don't block interactions
                        }}
                    />
                    {/* Inner intense glow */}
                    <path
                        d={edgePath}
                        style={{
                            stroke: activeColor,
                            strokeWidth: 8,
                            fill: 'none',
                            opacity: 0.6,
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
                    strokeWidth: isActive ? 3 : isCompleted ? 2 : 1,
                    fill: 'none',
                    filter: isActive ? `drop-shadow(0 0 4px ${activeColor})` : 'none',
                }}
                markerEnd={markerEnd}
            />

            {/* Animated circle that moves along the path when active */}
            {isActive && (
                <>
                    {/* Animated dot 1 */}
                    <circle r="6" fill={activeColor} filter={`drop-shadow(0 0 6px ${activeColor})`}>
                        <animateMotion
                            dur="1.5s"
                            repeatCount="indefinite"
                            path={edgePath}
                        />
                    </circle>
                    {/* Animated dot 2 (offset) */}
                    <circle r="4" fill={activeColor} opacity="0.6" filter={`drop-shadow(0 0 4px ${activeColor})`}>
                        <animateMotion
                            dur="1.5s"
                            repeatCount="indefinite"
                            path={edgePath}
                            begin="0.5s"
                        />
                    </circle>
                    {/* Animated dot 3 (offset) */}
                    <circle r="3" fill={activeColor} opacity="0.4">
                        <animateMotion
                            dur="1.5s"
                            repeatCount="indefinite"
                            path={edgePath}
                            begin="1s"
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
