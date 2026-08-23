import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@krutrim_agent/ui';
import { ChevronDown, Plus } from 'lucide-react';

export interface NewMenuProps {
  onNewChat: () => void;
  onNewAgent: () => void;
  onNewProject: () => void;
}

/** Replaces the old single "New chat" button — one consistent entry point for creating
 * any of the three top-level things a user can start (see the hierarchy plan). */
export function NewMenu({ onNewChat, onNewAgent, onNewProject }: NewMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="w-full justify-between gap-2">
          <span className="flex items-center gap-2">
            <Plus className="size-4" />
            New
          </span>
          <ChevronDown className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-48">
        <DropdownMenuItem onSelect={onNewChat}>New chat</DropdownMenuItem>
        <DropdownMenuItem onSelect={onNewAgent}>New agent</DropdownMenuItem>
        <DropdownMenuItem onSelect={onNewProject}>New project</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
