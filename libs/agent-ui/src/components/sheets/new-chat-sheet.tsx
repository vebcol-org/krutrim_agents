import { useState } from 'react';
import type { Project } from '@krutrim_agent/shared-types';
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

const STANDALONE_VALUE = '__standalone__';

export interface NewChatSheetProps {
  projects: Project[];
  defaultProjectId?: string | null;
  onCreate: (displayName: string, projectId: string | null) => void;
  onClose: () => void;
}

export function NewChatSheet({ projects, defaultProjectId, onCreate, onClose }: NewChatSheetProps) {
  const [displayName, setDisplayName] = useState('');
  const [projectId, setProjectId] = useState(defaultProjectId ?? STANDALONE_VALUE);

  function submit() {
    const trimmed = displayName.trim();
    if (!trimmed) return;
    onCreate(trimmed, projectId === STANDALONE_VALUE ? null : projectId);
    onClose();
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>New Chat</SheetTitle>
        </SheetHeader>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-chat-name">Name</Label>
          <Input
            id="new-chat-name"
            autoFocus
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="e.g. Quick question"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-chat-project">Project (optional)</Label>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger id="new-chat-project">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={STANDALONE_VALUE}>No project (standalone)</SelectItem>
              {projects.map((project) => (
                <SelectItem key={project.project_id} value={project.project_id}>
                  {project.project_title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button onClick={submit} disabled={!displayName.trim()}>
          Create chat
        </Button>
      </SheetContent>
    </Sheet>
  );
}
