import { useState } from 'react';
import type { Chat, Project } from '@krutrim_agent/shared-types';
import {
  Button,
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

export interface MoveChatSheetProps {
  chat: Chat;
  projects: Project[];
  onMove: (projectId: string | null) => void;
  onClose: () => void;
}

export function MoveChatSheet({ chat, projects, onMove, onClose }: MoveChatSheetProps) {
  const [projectId, setProjectId] = useState(chat.project_id ?? STANDALONE_VALUE);

  function submit() {
    onMove(projectId === STANDALONE_VALUE ? null : projectId);
    onClose();
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>Move &quot;{chat.display_name}&quot;</SheetTitle>
        </SheetHeader>

        <Select value={projectId} onValueChange={setProjectId}>
          <SelectTrigger>
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

        <Button onClick={submit}>Move</Button>
      </SheetContent>
    </Sheet>
  );
}
