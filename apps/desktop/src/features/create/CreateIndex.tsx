import React from "react";
import { useNavigate } from "react-router";
import { PageHeader, Tile } from "@panelflow/ui-v2";
import { paths, type CreateKind } from "../../app/routes";

const STUDIOS: Array<{ kind: CreateKind; title: string; subtitle: string; initials: string }> = [
  { kind: "new", title: "New project", subtitle: "Import manga pages and run the pipeline", initials: "NP" },
  { kind: "stories", title: "Original stories", subtitle: "Series, episodes and daily uploads", initials: "OS" },
  { kind: "anime", title: "Anime review", subtitle: "Review an episode with narration", initials: "AR" },
  { kind: "chronoflow", title: "ChronoFlow", subtitle: "Chain H3 clips into a long video", initials: "CF" },
  { kind: "image", title: "Create an image", subtitle: "Generate art for a project", initials: "GI" },
];

export const CreateIndex: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="mx-auto grid w-full max-w-5xl gap-6 p-6 md:p-8">
      <PageHeader title="Create" meta={<span>What do you want to make?</span>} />
      <div className="grid grid-cols-2 gap-5 md:grid-cols-3 lg:grid-cols-5">
        {STUDIOS.map((studio) => (
          <Tile key={studio.kind} title={studio.title} subtitle={studio.subtitle} fallbackText={studio.initials} onOpen={() => navigate(paths.create(studio.kind))} />
        ))}
      </div>
    </div>
  );
};
