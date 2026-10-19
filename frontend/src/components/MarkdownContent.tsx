'use client';

import React from 'react';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * Lightweight, robust markdown renderer for chat and activity outputs.
 * Correctly renders code blocks, inline code, links, bold, italic, bullet lists,
 * headers (h1-h4), horizontal rules, and line breaks without external dependencies.
 */
export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className = '' }) => {
  if (!content) return null;

  // Split content by code blocks ```lang ... ```
  const codeBlockRegex = /```([a-zA-Z0-9_-]*)\n?([\s\S]*?)```/g;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(renderTextAndLists(content.slice(lastIndex, match.index), `text-${lastIndex}`));
    }
    const lang = match[1] || 'code';
    const code = match[2];
    parts.push(
      <div
        key={`code-${match.index}`}
        className="my-2.5 rounded-lg overflow-hidden border border-slate-200 bg-slate-900 text-slate-100 text-xs font-mono max-w-full shadow-xs"
      >
        {lang && (
          <div className="px-3 py-1 bg-slate-800 text-[10px] uppercase font-semibold text-slate-400 border-b border-slate-700/60 flex items-center justify-between">
            <span>{lang}</span>
          </div>
        )}
        <pre className="p-3 overflow-x-auto whitespace-pre leading-relaxed max-w-full text-xs">
          <code>{code}</code>
        </pre>
      </div>
    );
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push(renderTextAndLists(content.slice(lastIndex), `text-${lastIndex}`));
  }

  return (
    <div className={`space-y-2 leading-relaxed text-xs sm:text-sm break-words [overflow-wrap:anywhere] min-w-0 max-w-full ${className}`}>
      {parts}
    </div>
  );
};

function renderTextAndLists(raw: string, keyPrefix: string): React.ReactNode {
  const lines = raw.split('\n');
  const elements: React.ReactNode[] = [];
  let inList = false;
  let listItems: React.ReactNode[] = [];

  const flushList = (idx: number) => {
    if (inList && listItems.length > 0) {
      elements.push(
        <ul key={`${keyPrefix}-ul-${idx}`} className="list-disc list-inside space-y-1 my-1.5 pl-1 text-slate-700">
          {listItems}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();

    // Horizontal Rule
    if (trimmed === '---' || trimmed === '***' || trimmed === '___') {
      flushList(idx);
      elements.push(
        <hr key={`hr-${idx}`} className="my-3 border-t border-slate-200" />
      );
      return;
    }

    // Check for bullet list (* or -)
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      inList = true;
      listItems.push(
        <li key={`li-${idx}`} className="leading-relaxed">
          {formatInline(trimmed.substring(2))}
        </li>
      );
      return;
    }

    // Numbered list
    if (/^\d+\.\s/.test(trimmed)) {
      flushList(idx);
      elements.push(
        <div key={`num-${idx}`} className="pl-2 leading-relaxed">
          {formatInline(trimmed)}
        </div>
      );
      return;
    }

    flushList(idx);

    // Headers
    if (trimmed.startsWith('#### ')) {
      elements.push(
        <h5 key={`h5-${idx}`} className="font-semibold text-slate-900 text-xs sm:text-sm pt-2 pb-0.5">
          {formatInline(trimmed.substring(5))}
        </h5>
      );
    } else if (trimmed.startsWith('### ')) {
      elements.push(
        <h4 key={`h4-${idx}`} className="font-bold text-slate-900 text-xs sm:text-sm pt-2.5 pb-1">
          {formatInline(trimmed.substring(4))}
        </h4>
      );
    } else if (trimmed.startsWith('## ')) {
      elements.push(
        <h3 key={`h3-${idx}`} className="font-bold text-slate-900 text-sm sm:text-base pt-3 pb-1 border-b border-slate-100">
          {formatInline(trimmed.substring(3))}
        </h3>
      );
    } else if (trimmed.startsWith('# ')) {
      elements.push(
        <h2 key={`h2-${idx}`} className="font-extrabold text-slate-900 text-base sm:text-lg pt-3 pb-1 border-b border-slate-100">
          {formatInline(trimmed.substring(2))}
        </h2>
      );
    } else if (trimmed === '') {
      elements.push(<div key={`empty-${idx}`} className="h-1" />);
    } else {
      elements.push(
        <p key={`p-${idx}`} className="leading-relaxed">
          {formatInline(line)}
        </p>
      );
    }
  });

  flushList(lines.length);
  return <React.Fragment key={keyPrefix}>{elements}</React.Fragment>;
}

function formatInline(text: string): React.ReactNode {
  // Regex matches:
  // 1. Markdown link: [text](url)
  // 2. Bold: **text**
  // 3. Inline code: `code`
  // 4. Italic: *text*
  const parts: React.ReactNode[] = [];
  const regex = /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      parts.push(text.slice(lastIdx, match.index));
    }
    const token = match[0];

    // Markdown link [link text](url)
    if (token.startsWith('[') && token.includes('](') && token.endsWith(')')) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
      if (linkMatch) {
        const linkText = linkMatch[1];
        const linkUrl = linkMatch[2];
        const isExternal = linkUrl.startsWith('http://') || linkUrl.startsWith('https://');
        parts.push(
          <a
            key={`a-${match.index}`}
            href={linkUrl}
            target={isExternal ? '_blank' : undefined}
            rel={isExternal ? 'noopener noreferrer' : undefined}
            className="text-indigo-600 hover:text-indigo-800 underline font-medium break-all"
          >
            {linkText}
          </a>
        );
      } else {
        parts.push(token);
      }
    } else if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(
        <strong key={`b-${match.index}`} className="font-semibold text-slate-900">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code
          key={`c-${match.index}`}
          className="px-1.5 py-0.5 rounded bg-slate-100 text-indigo-700 font-mono text-xs border border-slate-200 break-all"
        >
          {token.slice(1, -1)}
        </code>
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(
        <em key={`i-${match.index}`} className="italic text-slate-700">
          {token.slice(1, -1)}
        </em>
      );
    }
    lastIdx = match.index + token.length;
  }

  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx));
  }

  return parts;
}
