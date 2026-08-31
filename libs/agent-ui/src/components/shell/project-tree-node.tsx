import type { Agent, Chat, Project } from '@krutrim_agent/shared-types';
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@krutrim_agent/ui';
import { ChevronRight, FolderOpen, MoreVertical, Plus } from 'lucide-react';

import type { WorkspaceSelection } from '../../store/workspace-slice';
import { AgentTreeNode } from './agent-tree-node';
import { ChatTreeNode } from './chat-tree-node';

export interface ProjectTreeNodeProps {
  project: Project;
  agents: Agent[];
  chats: Chat[];
  expanded: boolean;
  onToggle: () => void;
  selection: WorkspaceSelection | null;
  onSelectAgent: (agentId: string) => void;
  onSelectChat: (chatId: string) => void;
  onRenameProject: () => void;
  onDeleteProject: () => void;
  onNewAgent: () => void;
  onNewChat: () => void;
  onRenameAgent: (agentId: string) => void;
  onDeleteAgent: (agentId: string) => void;
  onRenameChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  onMoveChat: (chatId: string) => void;
}

export function ProjectTreeNode({
  project,
  agents,
  chats,
  expanded,
  onToggle,
  selection,
  onSelectAgent,
  onSelectChat,
  onRenameProject,
  onDeleteProject,
  onNewAgent,
  onNewChat,
  onRenameAgent,
  onDeleteAgent,
  onRenameChat,
  onDeleteChat,
  onMoveChat,
}: ProjectTreeNodeProps) {
  return (
    <div>
      <div className="group flex items-center gap-1 rounded-md pr-1 text-sm text-foreground hover:bg-secondary">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-1.5 truncate px-2 py-1.5 text-left"
        >
          <ChevronRight className={`size-3.5 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`} />
          <FolderOpen className="size-3.5 shrink-0 text-primary" />
          <span className="truncate font-medium">{project.project_title}</span>
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="size-6 shrink-0 opacity-0 group-hover:opacity-100"
          aria-label={`New agent or chat in ${project.project_title}`}
          onClick={onNewAgent}
          title="New agent in this project"
        >
          <Plus className="size-3.5" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-6 shrink-0 opacity-0 group-hover:opacity-100 data-[state=open]:opacity-100"
              aria-label={`${project.project_title} options`}
            >
              <MoreVertical className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onSelect={onNewAgent}>New agent…</DropdownMenuItem>
            <DropdownMenuItem onSelect={onNewChat}>New chat…</DropdownMenuItem>
            <DropdownMenuItem onSelect={onRenameProject}>Rename</DropdownMenuItem>
            <DropdownMenuItem onSelect={onDeleteProject} className="text-destructive">
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {expanded && (
        <div className="ml-4 flex flex-col gap-0.5 border-l border-border pl-2">
          {agents.map((agent) => (
            <AgentTreeNode
              key={agent.agent_id}
              agent={agent}
              active={selection?.kind === 'agent' && selection.agentId === agent.agent_id}
              onSelect={() => onSelectAgent(agent.agent_id)}
              onRename={() => onRenameAgent(agent.agent_id)}
              onDelete={() => onDeleteAgent(agent.agent_id)}
            />
          ))}
          {chats.map((chat) => (
            <ChatTreeNode
              key={chat.chat_id}
              chat={chat}
              active={selection?.kind === 'chat' && selection.chatId === chat.chat_id}
              onSelect={() => onSelectChat(chat.chat_id)}
              onRename={() => onRenameChat(chat.chat_id)}
              onDelete={() => onDeleteChat(chat.chat_id)}
              onMove={() => onMoveChat(chat.chat_id)}
            />
          ))}
          {agents.length === 0 && chats.length === 0 && (
            <p className="px-2 py-1 text-xs text-muted-foreground">Empty — add an agent or chat.</p>
          )}
        </div>
      )}
    </div>
  );
}
