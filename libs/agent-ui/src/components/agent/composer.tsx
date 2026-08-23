import { useState } from 'react';
import { Button, Textarea } from '@krutrim_agent/ui';
import { SendHorizontal } from 'lucide-react';

export interface ComposerProps {
  disabled: boolean;
  onSend: (text: string) => void;
}

export function Composer({ disabled, onSend }: ComposerProps) {
  const [value, setValue] = useState('');

  function submit() {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue('');
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl items-end gap-2 border-t border-border p-4">
      <Textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask a question to get started…"
        rows={2}
        className="min-h-0"
        disabled={disabled}
      />
      <Button size="icon" onClick={submit} disabled={disabled || !value.trim()} aria-label="Send message">
        <SendHorizontal className="size-4" />
      </Button>
    </div>
  );
}
