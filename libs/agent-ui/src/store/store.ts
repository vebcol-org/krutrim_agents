import { configureStore } from '@reduxjs/toolkit';

import chatReducer from './chat-slice';
import workspaceReducer from './workspace-slice';

export const store = configureStore({
  reducer: {
    chat: chatReducer,
    workspace: workspaceReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
