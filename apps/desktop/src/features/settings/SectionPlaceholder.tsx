import React from "react";
import { EmptyState, GlassPanel } from "@panelflow/ui-v2";

/** Temporary body for a section whose task has not landed yet. */
export const SectionPlaceholder: React.FC = () => (
  <GlassPanel blur={false}>
    <EmptyState title="This section is being rebuilt" description="Its settings are not available here yet." />
  </GlassPanel>
);
