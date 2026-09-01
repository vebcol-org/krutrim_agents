import { useEffect, useState } from 'react';
import type { AgentMeta, ModelCard, ModelSelection, Project } from '@krutrim_agent/shared-types';
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

import { fetchModelCatalog } from '../../api';

const NEW_PROJECT_VALUE = '__new__';
const PROFILE_DEFAULT = '__profile_default__';
/** Only the primary role is user-selectable; subagent roles are a multi-agent
 * internal and keep the profile default. */
const PRIMARY_ROLE = 'main';

export interface NewAgentSheetResult {
  projectId: string;
  /** Set only when the user chose "create new project" instead of an existing one — the
   * caller creates the project first, then the agent inside it. */
  newProjectTitle?: string;
  agentKey: string;
  displayName: string;
  /** The primary-role model pick, if the user changed it — applied via
   * `PUT /api/providers/agents/{id}/main` right after the agent is created. */
  roleModels?: Record<string, ModelSelection>;
}

export interface NewAgentSheetProps {
  backendUrl: string;
  projects: Project[];
  agentProfiles: AgentMeta[];
  defaultProjectId?: string | null;
  onCreate: (result: NewAgentSheetResult) => void;
  onClose: () => void;
}

/** Agents always need a project (see the hierarchy plan) — this combines "pick an existing
 * project" and "create one inline" into a single flow: the project `<Select>` always offers
 * "+ Create new project…", which reveals a name field in place of picking one. Also lets the
 * user set a model per role up front (optional; defaults to the profile's own choice). */
export function NewAgentSheet({
  backendUrl,
  projects,
  agentProfiles,
  defaultProjectId,
  onCreate,
  onClose,
}: NewAgentSheetProps) {
  const [projectId, setProjectId] = useState(defaultProjectId ?? projects[0]?.project_id ?? NEW_PROJECT_VALUE);
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [agentKey, setAgentKey] = useState(agentProfiles[0]?.key ?? '');
  const [displayName, setDisplayName] = useState('');
  const [models, setModels] = useState<ModelCard[]>([]);
  // model id, or PROFILE_DEFAULT to leave the profile's own choice
  const [modelChoice, setModelChoice] = useState<string>(PROFILE_DEFAULT);

  useEffect(() => {
    let cancelled = false;
    fetchModelCatalog(backendUrl, { kind: 'chat' })
      .then((c) => !cancelled && setModels(c))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [backendUrl]);

  const creatingNewProject = projectId === NEW_PROJECT_VALUE;
  const trimmedNewProjectTitle = newProjectTitle.trim();
  const canSubmit =
    displayName.trim().length > 0 &&
    agentKey.length > 0 &&
    (!creatingNewProject || trimmedNewProjectTitle.length > 0);

  function submit() {
    if (!canSubmit) return;
    const card = modelChoice === PROFILE_DEFAULT ? undefined : models.find((m) => m.id === modelChoice);
    onCreate({
      projectId,
      newProjectTitle: creatingNewProject ? trimmedNewProjectTitle : undefined,
      agentKey,
      displayName: displayName.trim(),
      roleModels: card ? { [PRIMARY_ROLE]: { provider: card.provider, model: card.id } } : undefined,
    });
    onClose();
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined} className="overflow-y-auto">
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

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-agent-model">Model (optional)</Label>
          <Select value={modelChoice} onValueChange={setModelChoice}>
            <SelectTrigger id="new-agent-model">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={PROFILE_DEFAULT}>Profile default</SelectItem>
              {models.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button onClick={submit} disabled={!canSubmit}>
          Create agent
        </Button>
      </SheetContent>
    </Sheet>
  );
}
