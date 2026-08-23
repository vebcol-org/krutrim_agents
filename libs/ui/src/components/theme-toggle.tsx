import { Moon, Sun } from 'lucide-react';

import { Button, type ButtonProps } from '../lib/button';
import { useTheme } from './theme-provider';

export function ThemeToggle({ className, ...props }: Omit<ButtonProps, 'onClick' | 'children'>) {
  const { theme, toggleTheme } = useTheme();

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={className}
      onClick={toggleTheme}
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      {...props}
    >
      {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  );
}
