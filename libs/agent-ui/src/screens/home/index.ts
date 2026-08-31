import type { AgentScreenModule } from '../types';
import { HomeScreen } from './home-screen';

/** The empty state — nothing open. */
export const homeScreen: AgentScreenModule = {
  key: 'home',
  displayName: 'Home',
  Center: HomeScreen,
};
