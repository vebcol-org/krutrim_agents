import { useState } from 'react';
import { Button, Input, Label, Sheet, SheetContent, SheetHeader, SheetTitle } from '@krutrim_agent/ui';

export interface NewProjectSheetProps {
  onCreate: (title: string) => void;
  onClose: () => void;
}

export function NewProjectSheet({ onCreate, onClose }: NewProjectSheetProps) {
  const [title, setTitle] = useState('');

  function submit() {
    const trimmed = title.trim();
    if (!trimmed) return;
    onCreate(trimmed);
    onClose();
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>New Project</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-project-title">Name</Label>
          <Input
            id="new-project-title"
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="e.g. Anthropic"
          />
        </div>
        <Button onClick={submit} disabled={!title.trim()}>
          Create project
        </Button>
      </SheetContent>
    </Sheet>
  );
}
