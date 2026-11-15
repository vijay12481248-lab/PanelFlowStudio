import React from "react";
import { Chip } from "../primitives/Chip";

export const EngineStatus: React.FC<{ connected: boolean; version?: string; gpu?: string }> = ({ connected, version, gpu }) => (
  <div className="flex items-center gap-2">
    <Chip tone={connected ? "ok" : "bad"} icon={<span aria-hidden="true" className={connected ? "size-1.5 rounded-full bg-ok" : "size-1.5 rounded-full bg-bad"} />}>
      {connected ? "Engine ready" : "Engine offline"}
    </Chip>
    {connected && version && <Chip>{version}</Chip>}
    {connected && gpu && <Chip>{`GPU ${gpu}`}</Chip>}
  </div>
);
