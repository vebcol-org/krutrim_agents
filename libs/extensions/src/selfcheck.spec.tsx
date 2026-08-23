import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import { ExtensionProvider } from './provider';
import { ExtensionSelfCheck } from './selfcheck';
import { ANONYMOUS_PRINCIPAL, type AuthProvider } from './types';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mockExtensionStatus(body: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => body,
    }),
  );
}

describe('ExtensionSelfCheck', () => {
  it('renders nothing when frontend and backend agree (both no-op/community)', async () => {
    mockExtensionStatus({
      edition: 'community',
      hooks: { RequestAuthenticator: 'NoOpRequestAuthenticator' },
      storage_backend: 'local',
      sandbox_runtime: 'docker',
    });

    render(
      <ExtensionProvider>
        <ExtensionSelfCheck backendUrl="http://backend.example" />
      </ExtensionProvider>,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalledWith('http://backend.example/api/system/extensions'));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders a warning banner when the frontend has a real auth provider but the backend reports no-op', async () => {
    mockExtensionStatus({
      edition: 'community',
      hooks: { RequestAuthenticator: 'NoOpRequestAuthenticator' },
      storage_backend: 'local',
      sandbox_runtime: 'docker',
    });

    const realAuthProvider: AuthProvider = {
      getPrincipal: () => ANONYMOUS_PRINCIPAL,
    };

    render(
      <ExtensionProvider hooks={{ authProvider: realAuthProvider }}>
        <ExtensionSelfCheck backendUrl="http://backend.example" />
      </ExtensionProvider>,
    );

    const banner = await screen.findByRole('alert');
    expect(banner.textContent).toContain('Extension configuration drift detected');
  });

  it('renders a warning banner when the backend reports real auth but the frontend has none configured', async () => {
    mockExtensionStatus({
      edition: 'extended',
      hooks: { RequestAuthenticator: 'SsoRequestAuthenticator' },
      storage_backend: 'local',
      sandbox_runtime: 'docker',
    });

    render(
      <ExtensionProvider>
        <ExtensionSelfCheck backendUrl="http://backend.example" />
      </ExtensionProvider>,
    );

    const banner = await screen.findByRole('alert');
    expect(banner.textContent).toContain('extended');
  });

  it('stays silent if the backend is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('network error')),
    );

    render(
      <ExtensionProvider>
        <ExtensionSelfCheck backendUrl="http://backend.example" />
      </ExtensionProvider>,
    );

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
