export const state = {
  page: "overview",
  conversationId: localStorage.getItem("eiva.conversation") || null,
  tasks: [],
  agents: [],
  approvals: [],
  voiceEnabled: false,
  events: new Map(),
  visionFile: null,
};

export function setConversation(id) {
  state.conversationId = id;
  if (id) localStorage.setItem("eiva.conversation", id);
  else localStorage.removeItem("eiva.conversation");
}
