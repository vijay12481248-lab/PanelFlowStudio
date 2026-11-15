import React from "react";
import { useNavigate } from "react-router";
import { api } from "@panelflow/api-client";
import { Button, GlassPanel, ListRow } from "@panelflow/ui-v2";
import { paths } from "../../app/routes";
import { useCreations } from "../data/queries";

/** Original Stories and ChronoFlow videos are saved as files, so the project list cannot show them. */
export const CreationsSection: React.FC = () => {
  const navigate = useNavigate();
  const { stories, chronoJobs, failed } = useCreations();
  const [problem, setProblem] = React.useState<string | null>(null);
  if (stories.length === 0 && chronoJobs.length === 0 && !failed) return null;

  const open = (slug: string, target: "folder" | "video") =>
    api.openOriginalStory(slug, target).catch(() => setProblem("Couldn't open that. Check that the file still exists."));

  return (
    <section aria-label="Creations" className="grid gap-3 grid-cols-1">
      <div>
        <h2 className="font-display text-base font-semibold text-fg">Creations</h2>
        <p className="text-sm text-fg-dim">Original Stories and ChronoFlow videos, saved as files next to your projects.</p>
        {failed && <p className="text-xs text-warn">Some creations could not be loaded. Is the engine running?</p>}
        {problem && <p role="alert" className="text-xs text-bad">{problem}</p>}
      </div>
      <GlassPanel blur={false} className="grid gap-1 p-2 grid-cols-1">
        {stories.map((story) => (
          <ListRow
            key={story.slug}
            title={story.title}
            subtitle={`${story.genre}, ${story.panels} panels`}
            action={
              <span className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => void open(story.slug, "folder")}>Open folder</Button>
                {story.has_video && <Button size="sm" variant="ghost" onClick={() => void open(story.slug, "video")}>Play video</Button>}
              </span>
            }
          />
        ))}
        {chronoJobs.map((job) => (
          <ListRow
            key={job.id}
            title={`ChronoFlow video ${job.id.slice(0, 8)}`}
            subtitle={job.prompt?.slice(0, 80) ?? "No prompt saved"}
            onSelect={() => navigate(paths.chronoflow({ jobId: job.id }))}
          />
        ))}
      </GlassPanel>
    </section>
  );
};
