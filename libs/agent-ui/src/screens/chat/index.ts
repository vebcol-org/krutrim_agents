import type { AgentScreenModule } from '../types';
import { ChatScreen } from './chat-screen';

/** The plain (non-agentic) chat flow. */
export const chatScreen: AgentScreenModule = {
  key: 'chat',
  displayName: 'Chat',
  Center: ChatScreen,
};
