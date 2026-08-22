// Re-export the native module. On web, it will be resolved to OraNotificationListenerModule.web.ts
// and on native platforms to OraNotificationListenerModule.ts
export { default } from './src/OraNotificationListenerModule';
export * from './src/OraNotificationListener.types';
