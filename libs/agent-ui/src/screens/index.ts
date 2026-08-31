// The screen framework's public surface. Built-in screens are registered
// eagerly in `./registry`; `registerScreen` there lets an external consumer add
// its own agent type. To add a screen in-tree: a `screens/<key>/` folder
// exporting an `AgentScreenModule`, plus one line in `./registry`.
export * from './types';
export * from './registry';
