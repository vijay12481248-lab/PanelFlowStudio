import { describe, expect, it } from "vitest";
import type { Project } from "@panelflow/shared-types";
import { groupBySeries } from "../ProjectsWorkspace";

const p = (title: string) => ({ id: title, title } as Project);

describe("groupBySeries", () => {
  it("groups chapters of one series in chapter order and leaves singles out", () => {
    const { groups, singles } = groupBySeries([
      p("Magic Emperor - Chapter 928 - B - ManhuaPlus"),
      p("Tales Of Demons And Gods - Chapter 536.1 - X"),
      p("Magic Emperor - Chapter 927 - A - ManhuaPlus"),
      p("Standalone"),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].series).toBe("Magic Emperor");
    expect(groups[0].projects.map((x) => x.title)).toEqual([
      "Magic Emperor - Chapter 927 - A - ManhuaPlus",
      "Magic Emperor - Chapter 928 - B - ManhuaPlus",
    ]);
    expect(singles.map((x) => x.title)).toEqual(["Tales Of Demons And Gods - Chapter 536.1 - X", "Standalone"]);
  });
});
