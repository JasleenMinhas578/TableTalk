import { Database, MessageCircle, Ban, TableProperties } from "lucide-react";

const INTENTS = {
  sql: { label: "Data query", icon: Database },
  dataset: { label: "About your data", icon: TableProperties },
  small_talk: { label: "Chat", icon: MessageCircle },
  off_topic: { label: "Out of scope", icon: Ban },
};

const LAYERS = {
  rules: "Decided by a quick rule",
  classifier: "Decided by the classifier",
  llm: "Decided by the language model",
};

export default function IntentBadge({ intent, route }) {
  const info = INTENTS[intent];
  if (!info) return null;
  const Icon = info.icon;

  let title = LAYERS[route?.layer] || "";
  if (route?.layer === "classifier" && route.confidence) {
    title += ` (${Math.round(route.confidence * 100)}% sure)`;
  }

  return (
    <span className={`intent intent--${intent}`} title={title}>
      <Icon size={13} aria-hidden="true" />
      {info.label}
    </span>
  );
}
