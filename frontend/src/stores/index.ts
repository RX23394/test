import { createPinia, type Pinia } from "pinia";

export const pinia: Pinia = createPinia();

export { useAuthStore } from "./auth";
export { useAdminStore } from "./admin";
export { useChatStore } from "./chat";
export { useConversationStore } from "./conversation";
export { useDocumentStore } from "./document";
