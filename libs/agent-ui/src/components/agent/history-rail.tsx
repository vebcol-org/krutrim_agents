import { useState } from 'react';
import type { Chat } from '@krutrim_agent/shared-types';
import { Avatar, Button, ScrollArea, Separator, ThemeToggle } from '@krutrim_agent/ui';
import { ChevronsLeft, ChevronsRight, Plus } from 'lucide-react';

import { MoveChatSheet, NewAgentSheet, NewChatSheet, NewProjectSheet } from '../creation-sheets';
import type { UseWorkspaceResult } from '../../hooks/use-workspace';
import { ChatTreeNode } from './chat-tree-node';
import { NewMenu } from './new-menu';
import { ProjectTreeNode } from './project-tree-node';

export interface HistoryRailProps {
  collapsed: boolean;
  onToggle: () => void;
  backendUrl: string;
  workspace: UseWorkspaceResult;
  /** Bridges a chat-tree selection into `chat-slice`'s message-loading flow — called in
   * addition to `workspace.selectChat`, which only updates tree highlighting/selection kind.
   * See `agent-layout.tsx`. */
  onOpenChatSession: (chatId: string) => void;
}

type ActiveSheet =
  | { kind: 'new-project' }
  | { kind: 'new-chat'; defaultProjectId: string | null }
  | { kind: 'new-agent'; defaultProjectId: string | null }
  | { kind: 'move-chat'; chat: Chat };

export function HistoryRail({ collapsed, onToggle, backendUrl, workspace, onOpenChatSession }: HistoryRailProps) {
  const [activeSheet, setActiveSheet] = useState<ActiveSheet | null>(null);

  function handleSelectChat(chatId: string) {
    workspace.selectChat(chatId);
    onOpenChatSession(chatId);
  }

  function handleRenameProject(projectId: string, currentTitle: string) {
    const next = window.prompt('Rename project', currentTitle);
    if (next && next.trim()) workspace.renameProjectTitle(projectId, next.trim());
  }

  function handleDeleteProject(projectId: string, title: string) {
    if (window.confirm(`Delete project "${title}"? This deletes every agent and chat inside it.`)) {
      workspace.deleteProject(projectId);
    }
  }

  function handleRenameAgent(projectId: string, agentId: string, currentName: string) {
    const next = window.prompt('Rename agent', currentName);
    if (next && next.trim()) workspace.renameAgentName(projectId, agentId, next.trim());
  }

  function handleDeleteAgent(projectId: string, agentId: string, name: string) {
    if (window.confirm(`Delete agent "${name}"?`)) workspace.deleteAgent(projectId, agentId);
  }

  function handleRenameChat(chatId: string, currentName: string) {
    const next = window.prompt('Rename chat', currentName);
    if (next && next.trim()) workspace.renameChatName(chatId, next.trim());
  }

  function handleDeleteChat(chatId: string, name: string) {
    if (window.confirm(`Delete chat "${name}"?`)) workspace.deleteChat(chatId);
  }

  if (collapsed) {
    return (
      <aside className="flex w-14 shrink-0 flex-col items-center gap-3 border-r border-border bg-card py-3">
        <span className="size-2 animate-pulse rounded-full bg-primary shadow-[0_0_0_3px_rgba(232,163,61,0.12)]" />
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Expand sidebar">
          <ChevronsRight className="size-4" />
        </Button>
        <Separator className="w-6" />
        <Button variant="ghost" size="icon" aria-label="Expand to create" onClick={onToggle}>
          <Plus className="size-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border bg-card">
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2 font-mono text-xs tracking-wide text-muted-foreground">
          <span className="size-2 animate-pulse rounded-full bg-primary shadow-[0_0_0_3px_rgba(232,163,61,0.12)]" />
          <span className="text-foreground">AGENT PLATFORM</span>
        </div>
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Collapse sidebar">
          <ChevronsLeft className="size-4" />
        </Button>
      </header>

      <div className="flex flex-col gap-2 px-3 pt-3">
        <NewMenu
          onNewChat={() => setActiveSheet({ kind: 'new-chat', defaultProjectId: null })}
          onNewAgent={() => setActiveSheet({ kind: 'new-agent', defaultProjectId: null })}
          onNewProject={() => setActiveSheet({ kind: 'new-project' })}
        />
      </div>

      <ScrollArea className="flex-1 px-3 py-3">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <span className="px-2 pb-1 font-mono text-[11px] uppercase tracking-widest text-border">Projects</span>
            {workspace.projects.length === 0 && (
              <p className="px-2 text-xs text-muted-foreground">No projects yet.</p>
            )}
            {workspace.projects.map((project) => (
              <ProjectTreeNode
                key={project.project_id}
                project={project}
                agents={workspace.agentsByProject[project.project_id] ?? []}
                chats={workspace.chatsByProject[project.project_id] ?? []}
                expanded={workspace.expandedProjectIds.includes(project.project_id)}
                onToggle={() => workspace.toggleProjectExpanded(project.project_id)}
                selection={workspace.selection}
                onSelectAgent={workspace.openAgent}
                onSelectChat={handleSelectChat}
                onRenameProject={() => handleRenameProject(project.project_id, project.project_title)}
                onDeleteProject={() => handleDeleteProject(project.project_id, project.project_title)}
                onNewAgent={() => setActiveSheet({ kind: 'new-agent', defaultProjectId: project.project_id })}
                onNewChat={() => setActiveSheet({ kind: 'new-chat', defaultProjectId: project.project_id })}
                onRenameAgent={(agentId) => {
                  const agent = workspace.agentsByProject[project.project_id]?.find((a) => a.agent_id === agentId);
                  if (agent) handleRenameAgent(project.project_id, agentId, agent.display_name);
                }}
                onDeleteAgent={(agentId) => {
                  const agent = workspace.agentsByProject[project.project_id]?.find((a) => a.agent_id === agentId);
                  if (agent) handleDeleteAgent(project.project_id, agentId, agent.display_name);
                }}
                onRenameChat={(chatId) => {
                  const chat = workspace.chatsByProject[project.project_id]?.find((c) => c.chat_id === chatId);
                  if (chat) handleRenameChat(chatId, chat.display_name);
                }}
                onDeleteChat={(chatId) => {
                  const chat = workspace.chatsByProject[project.project_id]?.find((c) => c.chat_id === chatId);
                  if (chat) handleDeleteChat(chatId, chat.display_name);
                }}
                onMoveChat={(chatId) => {
                  const chat = workspace.chatsByProject[project.project_id]?.find((c) => c.chat_id === chatId);
                  if (chat) setActiveSheet({ kind: 'move-chat', chat });
                }}
              />
            ))}
          </div>

          <div className="flex flex-col gap-1">
            <span className="px-2 pb-1 font-mono text-[11px] uppercase tracking-widest text-border">Chats</span>
            {workspace.standaloneChats.length === 0 && (
              <p className="px-2 text-xs text-muted-foreground">No chats yet — send a message to start one.</p>
            )}
            {workspace.standaloneChats.map((chat) => (
              <ChatTreeNode
                key={chat.chat_id}
                chat={chat}
                active={workspace.selection?.kind === 'chat' && workspace.selection.chatId === chat.chat_id}
                onSelect={() => handleSelectChat(chat.chat_id)}
                onRename={() => handleRenameChat(chat.chat_id, chat.display_name)}
                onDelete={() => handleDeleteChat(chat.chat_id, chat.display_name)}
                onMove={() => setActiveSheet({ kind: 'move-chat', chat })}
              />
            ))}
          </div>
        </div>
      </ScrollArea>

      <Separator />
      <div className="flex items-center gap-2 px-3 py-3">
        <Avatar label="Vishesh Panchal" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-foreground">Vishesh Panchal</p>
          <p className="truncate text-xs text-muted-foreground">visheshpanchal145@gmail.com</p>
        </div>
        <ThemeToggle />
      </div>

      {activeSheet?.kind === 'new-project' && (
        <NewProjectSheet onCreate={workspace.createProject} onClose={() => setActiveSheet(null)} />
      )}
      {activeSheet?.kind === 'new-chat' && (
        <NewChatSheet
          projects={workspace.projects}
          defaultProjectId={activeSheet.defaultProjectId}
          onCreate={(displayName, projectId) => workspace.createChat(displayName, projectId)}
          onClose={() => setActiveSheet(null)}
        />
      )}
      {activeSheet?.kind === 'new-agent' && (
        <NewAgentSheet
          backendUrl={backendUrl}
          projects={workspace.projects}
          agentProfiles={workspace.agentProfiles}
          defaultProjectId={activeSheet.defaultProjectId}
          onCreate={workspace.createAgent}
          onClose={() => setActiveSheet(null)}
        />
      )}
      {activeSheet?.kind === 'move-chat' && (
        <MoveChatSheet
          chat={activeSheet.chat}
          projects={workspace.projects}
          onMove={(projectId) => workspace.moveChat(activeSheet.chat.chat_id, projectId)}
          onClose={() => setActiveSheet(null)}
        />
      )}
    </aside>
  );
}
