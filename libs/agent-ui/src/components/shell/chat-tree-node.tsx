import type { Chat } from '@krutrim_agent/shared-types';
import {
  Button,
  cn,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@krutrim_agent/ui';
import { MessageSquare, MoreVertical } from 'lucide-react';

export interface ChatTreeNodeProps {
  chat: Chat;
  active: boolean;
  onSelect: () => void;
  onRename: () => void;
  onDelete: () => void;
  /** Opens the move picker — works both directions (into a project, or back to standalone). */
  onMove: () => void;
}

export function ChatTreeNode({ chat, active, onSelect, onRename, onDelete, onMove }: ChatTreeNodeProps) {
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
        <MessageSquare className="size-3.5 shrink-0" />
        <span className="truncate">{chat.display_name}</span>
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="size-6 shrink-0 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100"
            aria-label={`${chat.display_name} options`}
          >
            <MoreVertical className="size-3.5" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuItem onSelect={onRename}>Rename</DropdownMenuItem>
          <DropdownMenuItem onSelect={onMove}>Move to project…</DropdownMenuItem>
          <DropdownMenuItem onSelect={onDelete} className="text-destructive">
            Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
