import type { Agent } from '@krutrim_agent/shared-types';
import {
  Button,
  cn,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@krutrim_agent/ui';
import { Bot, MoreVertical } from 'lucide-react';

export interface AgentTreeNodeProps {
  agent: Agent;
  active: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
}

export function AgentTreeNode({ agent, active, onSelect, onRename, onDelete }: AgentTreeNodeProps) {
  return (
    <div
      className={cn(
        'group flex items-center gap-1 rounded-md pr-1 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground',
        active && 'bg-secondary text-foreground',
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-1.5 truncate px-2 py-1.5 text-left"
      >
        <Bot className="size-3.5 shrink-0" />
        <span className="truncate">{agent.display_name}</span>
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-border">{agent.agent_key}</span>
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-6 shrink-0 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100"
            aria-label={`${agent.display_name} options`}
          >
            <MoreVertical className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={onRename}>Rename</DropdownMenuItem>
          <DropdownMenuItem onSelect={onDelete} className="text-destructive">
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
