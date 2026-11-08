import React from "react";
import { useNavigate } from "react-router";
import { Button, EmptyState, GlassPanel, PageHeader } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";

/** There is no standalone library yet: music and sound effects are picked inside the story editor. */
export const LibraryPage: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="mx-auto grid w-full max-w-3xl gap-6 p-6 md:p-8">
      <PageHeader title="Library" />
      <GlassPanel>
        <EmptyState
          title="The library opens inside the story editor"
          description="Pick music and sound effects from the audio panel while you edit a video. A standalone library for all your assets comes later."
          action={<Button variant="primary" onClick={() => navigate(paths.projects())}>Open projects</Button>}
        />
      </GlassPanel>
    </div>
  );
};
