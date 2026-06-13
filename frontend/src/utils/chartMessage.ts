import type { ChartSpec } from '../types';

const CHART_PREFIX = '<!--chart:';

export function parseMessageContent(content: string): {
  chart?: ChartSpec;
  content: string;
} {
  if (!content.startsWith(CHART_PREFIX)) {
    return { content };
  }

  const end = content.indexOf('-->');
  if (end === -1) {
    return { content };
  }

  try {
    const chart = JSON.parse(
      content.slice(CHART_PREFIX.length, end),
    ) as ChartSpec;
    const text = content.slice(end + 3).replace(/^\n/, '');
    return { chart, content: text };
  } catch {
    return { content };
  }
}

export function formatAxisValue(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 10_000) {
    return `${(value / 10_000).toFixed(1)}万`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}k`;
  }
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}
