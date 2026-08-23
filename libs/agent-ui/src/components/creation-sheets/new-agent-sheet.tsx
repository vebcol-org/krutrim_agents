import { useState } from 'react';
import type { AgentMeta, Project } from '@krutrim_agent/shared-types';
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@krutrim_agent/ui';

const NEW_PROJECT_VALUE = '__new__';

export interface NewAgentSheetResult {
  projectId: string;
  /** Set only when the user chose "create new project" instead of an existing one — the
   * caller creates the project first, then the agent inside it. */
  newProjectTitle?: string;
  agentKey: string;
  displayName: string;
}

export interface NewAgentSheetProps {
  projects: Project[];
  agentProfiles: AgentMeta[];
  defaultProjectId?: string | null;
  onCreate: (result: NewAgentSheetResult) => void;
  onClose: () => void;
}

/** Agents always need a project (see the hierarchy plan) — this combines "pick an existing
 * project" and "create one inline" into a single flow: the project `<Select>` always offers
 * "+ Create new project…", which reveals a name field in place of picking one. */
export function NewAgentSheet({ projects, agentProfiles, defaultProjectId, onCreate, onClose }: NewAgentSheetProps) {
  const [projectId, setProjectId] = useState(defaultProjectId ?? projects[0]?.project_id ?? NEW_PROJECT_VALUE);
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [agentKey, setAgentKey] = useState(agentProfiles[0]?.key ?? '');
  const [displayName, setDisplayName] = useState('');

  const creatingNewProject = projectId === NEW_PROJECT_VALUE;
  const trimmedNewProjectTitle = newProjectTitle.trim();
  const canSubmit = displayName.trim().length > 0 && agentKey.length > 0 && (!creatingNewProject || trimmedNewProjectTitle.length > 0);

  function submit() {
    if (!canSubmit) return;
    onCreate({
      projectId,
      newProjectTitle: creatingNewProject ? trimmedNewProjectTitle : undefined,
      agentKey,
      displayName: displayName.trim(),
    });
    onClose();
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>New Agent</SheetTitle>
        </SheetHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-agent-project">Project</Label>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger id="new-agent-project">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {projects.map((project) => (
                <SelectItem key={project.project_id} value={project.project_id}>
                  {project.project_title}
                </SelectItem>
              ))}
              <SelectItem value={NEW_PROJECT_VALUE}>+ Create new project…</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {creatingNewProject && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-agent-new-project-title">New project name</Label>
            <Input
              id="new-agent-new-project-title"
              autoFocus
              value={newProjectTitle}
              onChange={(e) => setNewProjectTitle(e.target.value)}
              placeholder="e.g. Anthropic"
            />
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-agent-key">Agent type</Label>
          <Select value={agentKey} onValueChange={setAgentKey}>
            <SelectTrigger id="new-agent-key">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {agentProfiles.map((profile) => (
                <SelectItem key={profile.key} value={profile.key}>
                  {profile.display_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-agent-name">Name</Label>
          <Input
            id="new-agent-name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="e.g. Company Business Analysis"
          />
        </div>

        <Button onClick={submit} disabled={!canSubmit}>
          Create agent
        </Button>
      </SheetContent>
    </Sheet>
  );
}
