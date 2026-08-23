import { useContext } from 'react';

import { ExtensionContext } from './provider';

export function useAuthProvider() {
  return useContext(ExtensionContext).authProvider;
}

export function useVisibilityFilter() {
  return useContext(ExtensionContext).visibilityFilter;
}
