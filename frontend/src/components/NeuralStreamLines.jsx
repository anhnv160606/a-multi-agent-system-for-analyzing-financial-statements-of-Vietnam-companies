import React, { useEffect, useState } from 'react';

export default function NeuralStreamLines({ isProcessing }) {
  const [paths, setPaths] = useState([]);

  useEffect(() => {
    const updatePaths = () => {
      const target = document.querySelector('[id^="aiCard-"]:last-child');
      const docs = [0, 1, 2, 3].map((i) => document.getElementById(`ragDocCard-${i}`)).filter(Boolean);

      if (!target || docs.length === 0) {
        setPaths([]);
        return;
      }

      const targetRect = target.getBoundingClientRect();
      const targetX = targetRect.right - 10;
      const targetY = targetRect.top + Math.min(targetRect.height / 2, 100);

      const colors = ['#06B6D4', '#818CF8', '#A855F7', '#10B981'];

      const newPaths = docs.map((doc, idx) => {
        const docRect = doc.getBoundingClientRect();
        const startX = docRect.left;
        const startY = docRect.top + docRect.height / 2;

        const deltaX = startX - targetX;
        const cp1X = startX - deltaX * 0.45;
        const cp1Y = startY;
        const cp2X = targetX + deltaX * 0.45;
        const cp2Y = targetY + (idx - 1.5) * 10;

        return {
          d: `M ${startX} ${startY} C ${cp1X} ${cp1Y}, ${cp2X} ${cp2Y}, ${targetX} ${targetY}`,
          color: colors[idx % colors.length],
          delay: `${idx * 0.25}s`,
        };
      });

      setPaths(newPaths);
    };

    updatePaths();
    window.addEventListener('resize', updatePaths);
    const timer = setTimeout(updatePaths, 300);

    return () => {
      window.removeEventListener('resize', updatePaths);
      clearTimeout(timer);
    };
  }, [isProcessing]);

  if (!paths.length) return null;

  return (
    <svg className="fixed inset-0 w-full h-full pointer-events-none z-20">
      {paths.map((p, idx) => (
        <path
          key={idx}
          d={p.d}
          fill="none"
          stroke={p.color}
          strokeWidth="1.6"
          strokeLinecap="round"
          className="opacity-75 animate-pulse"
          style={{ animationDuration: '2s', animationDelay: p.delay }}
        />
      ))}
    </svg>
  );
}
