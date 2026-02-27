'use client';

import { useState } from 'react';
import {
  BookOpen, ChevronRight, Search, Code2, Cpu, FileCode,
  Lightbulb, GraduationCap, X
} from 'lucide-react';
import { useIDEStore, SDK_DOCS } from '@/store/ideStore';
import ReactMarkdown from 'react-markdown';

const DOC_SECTIONS: { key: keyof typeof SDK_DOCS; label: string; icon: any }[] = [
  { key: 'overview', label: 'Overview', icon: BookOpen },
  { key: 'context', label: 'Context API', icon: Cpu },
  { key: 'manifest', label: 'Manifest', icon: FileCode },
  { key: 'patterns', label: 'Patterns', icon: Lightbulb },
  { key: 'imitation', label: 'Imitation Learning', icon: GraduationCap },
];

export default function DocsPanel() {
  const { activeDocSection, setActiveDocSection, setRightPanel } = useIDEStore();
  const [search, setSearch] = useState('');

  const doc = SDK_DOCS[activeDocSection];

  // Filter sections by search
  const filteredSections = search
    ? DOC_SECTIONS.filter(
        (s) =>
          s.label.toLowerCase().includes(search.toLowerCase()) ||
          SDK_DOCS[s.key].content.toLowerCase().includes(search.toLowerCase())
      )
    : DOC_SECTIONS;

  return (
    <div className="flex flex-col h-full bg-bg-secondary">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-bg-secondary border-b border-border-primary">
        <div className="flex items-center gap-2.5">
          <BookOpen size={15} className="text-accent" />
          <span className="text-sm font-medium text-text-primary">SDK Documentation</span>
        </div>
        <button
          onClick={() => setRightPanel('none')}
          className="p-1.5 text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated rounded-md transition-colors"
        >
          <X size={14} />
        </button>
      </div>

      {/* Search */}
      <div className="px-4 py-2.5 border-b border-border-primary">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search docs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 text-sm bg-bg-elevated border border-border-primary rounded-lg
                       text-text-primary placeholder:text-text-tertiary outline-none
                       focus:border-accent/40 transition-colors"
          />
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar nav */}
        <div className="w-44 border-r border-border-primary bg-bg-secondary overflow-y-auto py-2">
          {filteredSections.map((section) => {
            const Icon = section.icon;
            const isActive = activeDocSection === section.key;
            return (
              <button
                key={section.key}
                onClick={() => setActiveDocSection(section.key)}
                className={`
                  w-full flex items-center gap-2.5 px-4 py-2.5 text-sm transition-all
                  ${isActive
                    ? 'text-accent bg-accent-subtle border-r-2 border-accent font-medium'
                    : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated'
                  }
                `}
              >
                <Icon size={14} />
                <span>{section.label}</span>
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-5">
          <div className="prose prose-invert prose-sm max-w-none
                          prose-headings:text-text-primary
                          prose-h1:text-xl prose-h1:font-bold prose-h1:border-b prose-h1:border-border-primary prose-h1:pb-3 prose-h1:mb-5
                          prose-h2:text-base prose-h2:font-semibold prose-h2:text-accent prose-h2:mt-6 prose-h2:mb-3
                          prose-h3:text-sm prose-h3:font-medium prose-h3:mt-4 prose-h3:mb-2
                          prose-p:text-sm prose-p:text-text-secondary prose-p:leading-relaxed
                          prose-code:text-xs prose-code:bg-bg-elevated prose-code:text-accent prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
                          prose-pre:bg-bg-tertiary prose-pre:border prose-pre:border-border-primary prose-pre:rounded-xl prose-pre:text-xs
                          prose-table:text-sm
                          prose-th:text-text-secondary prose-th:font-medium prose-th:border-b prose-th:border-border-primary prose-th:pb-2
                          prose-td:text-text-tertiary prose-td:py-2 prose-td:border-b prose-td:border-border-primary/50
                          prose-strong:text-text-primary
                          prose-a:text-accent prose-a:no-underline hover:prose-a:underline
                          prose-li:text-sm prose-li:text-text-secondary
                          prose-ul:text-sm
                          "
          >
            <ReactMarkdown
              components={{
                code: ({ className, children, ...props }: any) => {
                  const isBlock = className?.includes('language-');
                  if (isBlock) {
                    return (
                      <pre className="bg-bg-tertiary border border-border-primary rounded-xl p-4 overflow-x-auto">
                        <code className="text-xs font-mono text-text-primary" {...props}>
                          {children}
                        </code>
                      </pre>
                    );
                  }
                  return (
                    <code className="text-xs bg-bg-elevated text-accent px-1.5 py-0.5 rounded font-mono" {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {doc.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}
